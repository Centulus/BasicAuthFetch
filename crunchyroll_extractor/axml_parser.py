"""Parse Android Binary XML (AXML) without external tools."""
import struct


def _read_string_pool(data: bytes, chunk_start: int) -> list[str]:
    hdr_size   = struct.unpack_from('<H', data, chunk_start + 2)[0]
    string_count = struct.unpack_from('<I', data, chunk_start + 8)[0]
    flags      = struct.unpack_from('<I', data, chunk_start + 16)[0]
    strings_start = struct.unpack_from('<I', data, chunk_start + 20)[0]
    utf8 = bool(flags & (1 << 8))

    offsets_base = chunk_start + hdr_size
    sdata_base   = chunk_start + strings_start

    strings: list[str] = []
    for i in range(string_count):
        off = struct.unpack_from('<I', data, offsets_base + i * 4)[0]
        p = sdata_base + off
        try:
            if utf8:
                cl = data[p]; p += 1
                if cl & 0x80: p += 1          # two-byte char-count
                bl = data[p]; p += 1
                if bl & 0x80:                 # two-byte byte-count
                    bl = ((bl & 0x7F) << 8) | data[p]; p += 1
                strings.append(data[p:p + bl].decode('utf-8', 'replace'))
            else:
                cl = struct.unpack_from('<H', data, p)[0]; p += 2
                if cl & 0x8000:               # two-word char-count
                    cl = ((cl & 0x7FFF) << 16) | struct.unpack_from('<H', data, p)[0]; p += 2
                strings.append(data[p:p + cl * 2].decode('utf-16-le', 'replace'))
        except Exception:
            strings.append('')
    return strings


_CHUNK_STRING_POOL = 0x0001
_CHUNK_START_ELEM  = 0x0102
_TYPE_STRING       = 0x03


def parse_manifest(axml_data: bytes) -> dict:
    """Parse a binary AndroidManifest.xml. Returns versionName, versionCode, is_tv."""
    result = {'versionName': None, 'versionCode': None, 'is_tv': False}
    if len(axml_data) < 8:
        return result

    magic = struct.unpack_from('<I', axml_data, 0)[0]
    if magic != 0x00080003:
        return result

    # --- first pass: collect string pool ---
    strings: list[str] = []
    pos = 8
    while pos < len(axml_data) - 8:
        chunk_type = struct.unpack_from('<H', axml_data, pos)[0]
        chunk_size = struct.unpack_from('<I', axml_data, pos + 4)[0]
        if chunk_size <= 0:
            break
        if chunk_type == _CHUNK_STRING_POOL:
            strings = _read_string_pool(axml_data, pos)
        pos += chunk_size

    if not strings:
        return result

    # Fast TV check: LEANBACK in the string pool is sufficient
    leanback = 'android.intent.category.LEANBACK_LAUNCHER'
    result['is_tv'] = any(leanback in s for s in strings)

    # --- second pass: parse <manifest> element for version attributes ---
    pos = 8
    while pos < len(axml_data) - 8:
        chunk_type = struct.unpack_from('<H', axml_data, pos)[0]
        chunk_hdr  = struct.unpack_from('<H', axml_data, pos + 2)[0]
        chunk_size = struct.unpack_from('<I', axml_data, pos + 4)[0]
        if chunk_size <= 0:
            break

        if chunk_type == _CHUNK_START_ELEM:
            name_idx = struct.unpack_from('<I', axml_data, pos + 20)[0]
            elem_name = strings[name_idx] if name_idx < len(strings) else ''
            if elem_name == 'manifest':
                attr_size  = struct.unpack_from('<H', axml_data, pos + 26)[0]
                attr_count = struct.unpack_from('<H', axml_data, pos + 28)[0]
                attr_base  = pos + chunk_hdr
                for j in range(attr_count):
                    aoff = attr_base + j * attr_size
                    if aoff + 20 > len(axml_data):
                        break
                    name_idx  = struct.unpack_from('<I', axml_data, aoff + 4)[0]
                    raw_idx   = struct.unpack_from('<I', axml_data, aoff + 8)[0]
                    val_type  = axml_data[aoff + 15]
                    val_data  = struct.unpack_from('<i', axml_data, aoff + 16)[0]
                    attr_name = strings[name_idx] if name_idx < len(strings) else ''

                    if attr_name == 'versionName':
                        if val_type == _TYPE_STRING and val_data < len(strings):
                            result['versionName'] = strings[val_data]
                        elif raw_idx != 0xFFFFFFFF and raw_idx < len(strings):
                            result['versionName'] = strings[raw_idx]
                    elif attr_name == 'versionCode':
                        result['versionCode'] = str(val_data)
                break  # <manifest> is always the first element
        pos += chunk_size

    return result
