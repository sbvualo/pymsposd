"""

"""
import argparse
import array
import enum
import io
import os
import struct
import typing


__version__ = '0.1.0'

__all__ = [
    'Reader',
    'Track'
]


OSD_VERSION = 1
OSD_MAGIC = b'MSPOSD\x00'
MAX_X = 60
MAX_Y = 22
MAX_T = MAX_X * MAX_Y


class Chars:
    ALT = 0x7F  # высота
    LAT = 0x89  # широто
    LON = 0x98  # долгота
    SPEED = 0x70  # скорость
    AMP = 0x9A  # ампер
    VOLT = 0x06  # вольт
    MAH = 0x07  # мА*ч
    METER = 0x0C  # метр
    KM = 0x7D  # километр
    MI = 0x7E  # миля
    MPH = 0x9D  # миль/ч
    KMPH = 0x9E  # км/ч
    MPS = 0x9F  # м/c
    LQ = 0x7B  # качество приема
    RSSI = 0x01  # RSSI
    SAT1 = 0x1E  # спутников (первая ячейка)
    SAT2 = 0x1F  # спутников (вторая ячейка)
    HOME = 0x11  # расстояние до дома
    TRIP = 0x71  # пройденный путь
    BAT0 = 0x90  # батарея с минимальным зарядом
    BAT1 = 0x91
    BAT2 = 0x92
    BAT3 = 0x93
    BAT4 = 0x94
    BAT5 = 0x95
    BAT6 = 0x96  # батарея с полным зарядом
    BAT = 0x97


class Frame:
    """
    Кадр OSD
    """
    HEADER_FMT = b'<II'
    HEADER_SIZE = struct.calcsize(HEADER_FMT)

    def __init__(self, data: bytes):
        self.rawdata = data
        values = struct.unpack(self.HEADER_FMT, data[:self.HEADER_SIZE])
        self.header = dict(zip(
            ('frame_idx', 'size'),
            values
        ))
        self.ar = array.array('H', data[self.HEADER_SIZE:])

    def __str__(self):
        sl = []
        for row in range(MAX_Y):
            for col in range(MAX_X):
                i = col * MAX_Y + row
                ch = self.code_to_char(self.ar[i])
                sl.append(ch)
            sl.append('\n')
        return ''.join(sl)

    @staticmethod
    def code_to_char(code):
        if code == 0:
            ch = '~'
        elif 0x20 <= code < 0x5f:
            ch = chr(code)
        else:
            ch = 'u'
        return ch

    def cell(self, x, y):
        if x >= MAX_X or y >= MAX_Y:
            raise ValueError
        return self.ar[x * MAX_Y + y]

    def __getitem__(self, item):
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError
        return self.cell(item[0], item[1])

    def line(self, y):
        if y < 0 or y >= MAX_Y:
            raise ValueError
        return tuple(self.ar[x * MAX_Y + y] for x in range(MAX_X))

    def sline(self, y):
        line = self.line(y)
        return ''.join(self.code_to_char(c) for c in line)

    def hex1(self):
        sl = []
        for row in range(MAX_Y):
            for col in range(MAX_X):
                i = col * MAX_Y + row
                code = self.ar[i]
                if code == 0:
                    ch = '  |'
                elif 0x20 <= code < 0x5f:
                    ch = chr(code) + ' |'
                else:
                    ch = '{:02X}|'.format(code)
                sl.append(ch)
            sl.append('\n')
        return ''.join(sl)

    def extract_value(self, tag, reverse=False, allowed_chars=b'0123456789.-: '):
        """
        Вырезает подстроку после или до символа tag
        :param tag: символ, начиная от которого вырезать
        :param reverse: если True, налево от символа
        :param allowed_chars: разрешенные символы
        :return: кортеж из вырезанной строки и следующего символа или (None, None) если строка не найдена
        """
        try:
            idx = self.ar.index(tag)
        except ValueError:
            return None, None
        x, y = idx // MAX_Y, idx % MAX_Y
        line = self.line(y)
        if reverse:
            line = line[::-1]
            x = MAX_X - 1 - x
        sl = bytearray()
        next_char = None
        for i in range(x + 1, len(line)):
            ch = line[i]
            if ch in allowed_chars:
                sl.append(ch)
            else:
                next_char = ch
                break
        if reverse:
            sl = sl[::-1]
            next_char = tag
        s = sl.decode('ascii')
        s = s.strip()
        return s, next_char


@enum.unique
class FontVariant(enum.Enum):
    """
    Варианты шрифта для разных полетных контроллеров
    """
    GENERIC = 0
    BETAFLIGHT = 1
    INAV = 2
    ARDUPILOT = 3
    KISS_ULTRA = 4
    QUICKSILVER = 5


class Reader:
    """
    Читалка OSD
    Поддерживает итерации по кадрам OSD
    """
    HEADER_FMT = b'<7sHBBBBHHB'
    HEADER_SIZE = struct.calcsize(HEADER_FMT)

    def __init__(self, fileobj: typing.BinaryIO):
        """
        :param fileobj: Файловый объект
        """
        self._fileobj = fileobj
        # Читать заголовок
        _header_data = fileobj.read(self.HEADER_SIZE)
        values = struct.unpack(self.HEADER_FMT, _header_data)
        self._header = dict(zip(
            ('magic', 'version', 'char_width', 'char_height', 'font_width', 'font_height', 'x_offset', 'y_offset',
             'font_variant'),
            values))
        if self._header['magic'] != OSD_MAGIC:
            raise ValueError('Incorrect magic in file header. expected: {}, got: {}'.format(OSD_MAGIC,
                                                                                            self._header['magic']))
        if self._header['version'] != OSD_VERSION:
            raise ValueError('Invalid osd file version. expected: {}, got: {}'.format(OSD_VERSION,
                                                                                      self._header['version']))
        self._iter_index = 0

    def __iter__(self):
        """
        Получить итератор по кадрам
        :return:
        """
        self._iter_index = 0
        return self

    def get_frame(self, index):
        frame_data_size = Frame.HEADER_SIZE + MAX_T * 2
        self._fileobj.seek(self.HEADER_SIZE + frame_data_size * index, io.SEEK_SET)
        frame_data = self._fileobj.read(frame_data_size)
        if len(frame_data) != frame_data_size:
            return None
        return Frame(frame_data)

    def __next__(self):
        """
        Очередной кадр
        :return:
        """
        frame = self.get_frame(self._iter_index)
        self._iter_index += 1
        if frame is None:
            raise StopIteration
        else:
            return frame

    def __getitem__(self, item):
        frame = self.get_frame(item)
        if frame is None:
            raise IndexError
        else:
            return frame


class Track:
    """
    Класс для извлечения трека из OSD
    """
    def __init__(self, osdpath: str, onerror='prev', fps=60):
        """
        :param osdpath: Путь к файлу OSD
        :param onerror: Действие при ошибке получения значения:
                        prev - предыдущее значение
                        skip - пропустить точку
                        empty - пустое значение
        :param fps: Частота кадров видео
        """
        self.header = ('latitude', 'longitude', 'altitude', 'speed', 'time_ms')
        self.points = []
        prev = [''] * len(self.header)
        with open(osdpath, 'rb') as fp:
            rd = Reader(fp)
            for fr in rd:
                frame_idx = fr.header['frame_idx']
                lat, _ = fr.extract_value(Chars.LAT)
                lon, _ = fr.extract_value(Chars.LON)
                alt, _ = fr.extract_value(Chars.ALT)
                spd, _ = fr.extract_value(Chars.SPEED)
                if all(v is None for v in (lat, lon, alt, spd)):
                    # Если не извлечено ни одного значения
                    continue
                if onerror == 'skip':
                    if any(i is None for i in (lat, lon, alt, spd)):
                        continue
                elif onerror == 'empty':
                    lat = lat or ''
                    lon = lon or ''
                    alt = alt or ''
                    spd = spd or ''
                elif onerror == 'prev':
                    lat = lat or prev[0]
                    lon = lon or prev[1]
                    alt = alt or prev[2]
                    spd = spd or prev[3]
                    prev[:4] = (lat, lon, alt, spd)
                ts = int(frame_idx * 1000 / fps)
                self.points.append([lat, lon, alt, spd, ts])

    def save_csv(self, csvpath, encoding='ascii', sep=',', eol='\n'):
        """
        Сохранить трек в CSV-файл
        :param encoding: Кодировка выходного файла
        :param sep: Разделитель колонок
        :param eol: Окончание строки
        :param csvpath: Путь к файлу csv
        :return:
        """
        with open(csvpath, 'w', encoding=encoding) as fp:
            fp.write(sep.join(self.header) + eol)
            for point in self.points:
                fp.write(sep.join(point[:-1]) + sep + str(point[-1]) + eol)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Parse GPS data from .osd (MSPOSD) file from DJI goggles',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-o', metavar='CSVFILE', dest='outputfile', default='output.csv', help='output .csv file')
    parser.add_argument('-f', dest='force', default=False, action='store_true',
                        help='Force overwrite output file if exists')
    parser.add_argument('inputfile', metavar='OSDFILE', help='input .osd file')
    args = parser.parse_args()
    trk = Track(args.inputfile, onerror='prev')
    if os.path.exists(args.outputfile) and not args.force:
        print('Error: File "{}" already exists'.format(args.outputfile))
        exit(1)
    trk.save_csv(args.outputfile)
    print('File "{}" written.'.format(args.outputfile))
    exit(0)
