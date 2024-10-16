"""

"""
import abc
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


class CharsBetaflight:
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


class CharsInav:
    # See https://github.com/iNavFlight/inav/blob/master/src/main/drivers/osd_symbols.h#L26
    LAT = 0x03
    LON = 0x04
    WATT = 0x71
    ALT = 0x76
    SPEED_KMPH = 0x90
    SPEED_MPH = 0x91
    SPEED_KT = 0x92


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

    @abc.abstractmethod
    def extract_value(self, tag, reverse=False, allowed_chars=b'0123456789.-: '):
        pass

    @abc.abstractmethod
    def extract_lat(self):
        pass

    @abc.abstractmethod
    def extract_lon(self):
        pass

    @abc.abstractmethod
    def extract_alt(self):
        pass

    @abc.abstractmethod
    def extract_speed(self):
        pass

    @abc.abstractmethod
    def extract_power(self):
        pass


class FrameBetaflight(Frame):
    """
    Кадр OSD Betaflight
    """

    Chars = CharsBetaflight

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

    def extract_lat(self):
        return self.extract_value(self.Chars.LAT)

    def extract_lon(self):
        return self.extract_value(self.Chars.LON)

    def extract_alt(self):
        return self.extract_value(self.Chars.ALT)

    def extract_speed(self):
        return self.extract_value(self.Chars.SPEED)

    def extract_power(self):
        digits = b'0123456789'
        for idx, v in enumerate(self.ar):
            if v == ord(b'W'):
                if self.ar[idx - MAX_Y] in digits:
                    if self.ar[idx + MAX_Y] in b'\x00 ':
                        x, y = idx // MAX_Y, idx % MAX_Y
                        line = self.line(y)
                        s = bytearray()
                        for i in range(x, -1, -1):
                            if line[i] in digits:
                                s.insert(0, line[i])
                        val = s.decode('ascii')
                        return val, ord(b'W')
        return None, None


class FrameInav(Frame):
    """
    Кадр OSD INAV
    """
    def extract_value(self, tag, reverse=False, allowed_chars=b'0123456789.-: '):
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
        half_point = False
        for i in range(x + 1, len(line)):
            ch = line[i]
            # Обработать цифры с точкой
            if reverse:
                if 0xA1 <= ch <= 0xAA:
                    if half_point:
                        chs = [ch - 0xA1 + ord(b'0')]
                        half_point = False
                    else:
                        chs = [ord(b'.'), ch - 0xA1 + ord(b'0')]
                elif 0xB1 <= ch <= 0xBA:
                    chs = [ch - 0xB1 + ord(b'0'), ord(b'.')]
                    half_point = True
                else:
                    half_point = False
                    chs = [ch]
            else:
                if 0xA1 <= ch <= 0xAA:
                    chs = [ch - 0xA1 + ord(b'0'), ord(b'.')]
                    half_point = True
                elif 0xB1 <= ch <= 0xBA:
                    if half_point:
                        half_point = False
                        chs = [ch - 0xB1 + ord(b'0')]
                    else:
                        chs = [ord(b'.'), ch - 0xB1 + ord(b'0')]
                else:
                    half_point = False
                    chs = [ch]
            if all(x in allowed_chars for x in chs):
                sl.extend(chs)
            else:
                next_char = ch
                break
        if reverse:
            sl = sl[::-1]
            next_char = tag
        s = sl.decode('ascii')
        s = s.strip()
        return s, next_char

    def extract_lat(self):
        return self.extract_value(CharsInav.LAT)

    def extract_lon(self):
        return self.extract_value(CharsInav.LON)

    def extract_alt(self):
        return self.extract_value(CharsInav.ALT, reverse=True)

    def extract_speed(self):
        for tag in (CharsInav.SPEED_KMPH, CharsInav.SPEED_MPH, CharsInav.SPEED_KT):
            v, u = self.extract_value(tag, reverse=True)
            if v:
                return v, u
        return None, None

    def extract_power(self):
        return self.extract_value(CharsInav.WATT, reverse=True)


@enum.unique
class FontVariant(enum.IntEnum):
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
        if self._header['font_variant'] == FontVariant.BETAFLIGHT:
            return FrameBetaflight(frame_data)
        elif self._header['font_variant'] == FontVariant.INAV:
            return FrameInav(frame_data)
        else:
            raise NotImplementedError('Font variant "{}" not supported yet'.format(self._header['font_variant']))

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
        self.header = ('latitude', 'longitude', 'altitude', 'speed', 'time_ms', 'power')
        self.points = []
        prev = [''] * len(self.header)
        with open(osdpath, 'rb') as fp:
            rd = Reader(fp)
            for fr in rd:
                frame_idx = fr.header['frame_idx']
                lat, _ = fr.extract_lat()
                lon, _ = fr.extract_lon()
                alt, _ = fr.extract_alt()
                spd, _ = fr.extract_speed()
                pwr, _ = fr.extract_power()
                if all(v is None for v in (lat, lon, alt, spd, pwr)):
                    # Если не извлечено ни одного значения
                    continue
                if onerror == 'skip':
                    if any(i is None for i in (lat, lon, alt, spd, pwr)):
                        continue
                elif onerror == 'empty':
                    lat = lat or ''
                    lon = lon or ''
                    alt = alt or ''
                    spd = spd or ''
                    pwr = pwr or ''
                elif onerror == 'prev':
                    lat = lat or prev[0]
                    lon = lon or prev[1]
                    alt = alt or prev[2]
                    spd = spd or prev[3]
                    pwr = pwr or prev[5]
                    prev = (lat, lon, alt, spd, None, pwr)
                ts = int(frame_idx * 1000 / fps)
                self.points.append([lat, lon, alt, spd, ts, pwr])

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
                fp.write(sep.join(str(x) for x in point) + eol)


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
