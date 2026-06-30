"""Extract Crunchyroll credentials from DEX files without decompilation."""
import re
import struct
import time
from typing import NamedTuple

from .config import TARGET_PATTERNS, TV_CONSTANTS_CLASS


# ─────────────────────────── credential regexes ─────────────────────────────

_RE_SECRET_MOBILE = re.compile(r'^[A-Za-z0-9_-]{30,33}$')
_RE_CLIENT_MOBILE = re.compile(r'^[A-Za-z0-9_]{20}$')
_RE_CLIENT_TV     = re.compile(r'^[A-Za-z0-9_\-]{18,24}$')
_RE_SECRET_TV     = re.compile(r'^[A-Za-z0-9_\-]{28,36}$')

# DEX const-string opcodes
_OP_CONST_STRING       = 0x1A   # 4-byte: opcode(1) reg(1) string_idx(2)
_OP_CONST_STRING_JUMBO = 0x1B   # 6-byte: opcode(1) reg(1) string_idx(4)


# ─────────────────────────── low-level DEX helpers ──────────────────────────

def _read_uleb128(data: bytes, pos: int) -> tuple[int, int]:
    result = 0; shift = 0
    while True:
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7


def _extract_strings(dex: bytes) -> list[str]:
    """Parse the DEX string pool and return all strings in order."""
    if dex[:4] != b'dex\n':
        return []
    n_str  = struct.unpack_from('<I', dex, 0x38)[0]
    off_str = struct.unpack_from('<I', dex, 0x3C)[0]
    strings: list[str] = []
    for i in range(n_str):
        off = struct.unpack_from('<I', dex, off_str + i * 4)[0]
        pos = off
        result = 0; shift = 0
        while True:
            b = dex[pos]; pos += 1
            result |= (b & 0x7F) << shift
            if not (b & 0x80): break
            shift += 7
        end = dex.index(b'\x00', pos)
        try:
            strings.append(dex[pos:end].decode('utf-8', 'replace'))
        except Exception:
            strings.append('')
    return strings


def _extract_types(dex: bytes, strings: list[str]) -> list[str]:
    """Parse the DEX type descriptor pool."""
    n = struct.unpack_from('<I', dex, 0x40)[0]
    off = struct.unpack_from('<I', dex, 0x44)[0]
    types: list[str] = []
    for i in range(n):
        sid = struct.unpack_from('<I', dex, off + i * 4)[0]
        types.append(strings[sid] if sid < len(strings) else '')
    return types


class _StringRef(NamedTuple):
    """A const-string reference inside a code item."""
    byte_offset: int   # offset within the instructions buffer
    string_id:   int


def _scan_code_item(insns: bytes, n_strings: int) -> list[_StringRef]:
    """Return all const-string refs (opcode 0x1A/0x1B) from an instruction buffer."""
    refs: list[_StringRef] = []
    j = 0
    ln = len(insns)
    while j < ln - 1:
        op = insns[j]
        if op == _OP_CONST_STRING and j + 3 < ln:
            sid = struct.unpack_from('<H', insns, j + 2)[0]
            if sid < n_strings:
                refs.append(_StringRef(j, sid))
            j += 4
        elif op == _OP_CONST_STRING_JUMBO and j + 5 < ln:
            sid = struct.unpack_from('<I', insns, j + 2)[0]
            if sid < n_strings:
                refs.append(_StringRef(j, sid))
            j += 6
        else:
            j += 2
    return refs


def _iter_class_methods(dex: bytes, strings: list[str], types: list[str]):
    """Yield (class_descriptor, access_flags, const_string_refs) for every method in the DEX."""
    n_cls  = struct.unpack_from('<I', dex, 0x60)[0]
    off_cls = struct.unpack_from('<I', dex, 0x64)[0]
    n_str  = len(strings)

    for i in range(n_cls):
        cd_off = off_cls + i * 32
        type_idx     = struct.unpack_from('<I', dex, cd_off)[0]
        class_data_off = struct.unpack_from('<I', dex, cd_off + 24)[0]
        if not class_data_off:
            continue
        class_name = types[type_idx] if type_idx < len(types) else '?'

        pos = class_data_off
        sf, pos  = _read_uleb128(dex, pos)
        iif, pos = _read_uleb128(dex, pos)
        dm, pos  = _read_uleb128(dex, pos)
        vm, pos  = _read_uleb128(dex, pos)

        for _ in range(sf + iif):       # skip fields
            _, pos = _read_uleb128(dex, pos)
            _, pos = _read_uleb128(dex, pos)

        for _ in range(dm + vm):
            _, pos   = _read_uleb128(dex, pos)    # method_idx_diff
            acc, pos = _read_uleb128(dex, pos)    # access_flags
            code_off, pos = _read_uleb128(dex, pos)
            if not code_off:
                continue
            insns_size = struct.unpack_from('<I', dex, code_off + 12)[0]
            insns = dex[code_off + 16: code_off + 16 + insns_size * 2]
            refs = _scan_code_item(insns, n_str)
            if refs:
                yield class_name, acc, refs


def _class_all_strings(dex: bytes, strings: list[str], types: list[str], class_desc: str) -> list[str]:
    """Collect all const-string values from every method in a specific class, in bytecode order."""
    collected: list[str] = []
    for cls, _acc, refs in _iter_class_methods(dex, strings, types):
        if cls == class_desc:
            collected.extend(strings[r.string_id] for r in refs)
    return collected


# ─────────────────────────── public extraction API ──────────────────────────

class DexExtractor:
    """Credential extractor that works directly on DEX binary data."""

    def __init__(self, verbose: bool = True):
        self._verbose = verbose

    def _log(self, msg: str) -> None:
        if self._verbose:
            print(msg)

    # ── TV ──────────────────────────────────────────────────────────────────

    def find_tv_credentials(self, dex_files: list[bytes]) -> tuple[str | None, str | None]:
        """Find TV client_id and client_secret from the API Constants class."""
        self._log(f"\n=== PHASE 2 (TV): SCANNING {len(dex_files)} DEX FILE(S) ===")
        t0 = time.time()

        for idx, dex in enumerate(dex_files):
            strings = _extract_strings(dex)
            if not strings:
                continue
            types = _extract_types(dex, strings)

            if not any(TV_CONSTANTS_CLASS in t for t in types):
                continue

            const_strings = _class_all_strings(dex, strings, types, TV_CONSTANTS_CLASS)
            if not const_strings:
                continue

            self._log(f"  [DEX {idx}] Found {TV_CONSTANTS_CLASS} → {len(const_strings)} strings")

            client_id = None
            secret_id = None
            for i, s in enumerate(const_strings):
                if client_id is None and _RE_CLIENT_TV.match(s) and '.' not in s:
                    client_id = s
                    for s2 in const_strings[i + 1: i + 9]:
                        if _RE_SECRET_TV.match(s2) and '.' not in s2:
                            secret_id = s2
                            break
                    if secret_id:
                        break

            if not secret_id:
                # fallback: first plausible secret in the whole class
                for s in const_strings:
                    if _RE_SECRET_TV.match(s) and '.' not in s and s != client_id:
                        secret_id = s
                        break

            if client_id and secret_id:
                self._log(f"  Client ID: {client_id}")
                self._log(f"  Secret ID: {secret_id}")
                self._log(f"  Extracted in {time.time() - t0:.2f}s")
                return client_id, secret_id

        self._log("  TV credentials not found in Constants class.")
        return None, None

    # ── Mobile ──────────────────────────────────────────────────────────────

    def find_mobile_credentials(self, dex_files: list[bytes]) -> tuple[str | None, str | None]:
        """Find mobile client_id and secret by scanning code items for target-pattern proximity."""
        self._log(f"\n=== PHASE 2 (MOBILE): SCANNING {len(dex_files)} DEX FILE(S) ===")
        t0 = time.time()

        best: tuple[str, str, int, float] | None = None   # (client, secret, hits, dist)

        for idx, dex in enumerate(dex_files):
            strings = _extract_strings(dex)
            if not strings:
                continue

            target_ids = {i for i, s in enumerate(strings) if any(p in s for p in TARGET_PATTERNS)}
            if not target_ids:
                continue

            types = _extract_types(dex, strings)
            self._log(f"  [DEX {idx}] {len(strings)} strings, {len(target_ids)} target-pattern hits")

            for _cls, _acc, refs in _iter_class_methods(dex, strings, types):
                target_hits = sum(1 for r in refs if r.string_id in target_ids)
                if target_hits < 2:
                    continue

                secrets = [r for r in refs if _RE_SECRET_MOBILE.match(strings[r.string_id])]
                clients = [r for r in refs if _RE_CLIENT_MOBILE.match(strings[r.string_id])]
                if not secrets or not clients:
                    continue

                # exclude target-pattern strings that happen to match the length regexes
                secrets = [r for r in secrets if strings[r.string_id] not in TARGET_PATTERNS]
                clients = [r for r in clients if strings[r.string_id] not in TARGET_PATTERNS]
                if not secrets or not clients:
                    continue

                for sr in secrets:
                    for cr in clients:
                        dist = abs(sr.byte_offset - cr.byte_offset)
                        if best is None or target_hits > best[2] or (
                                target_hits == best[2] and dist < best[3]):
                            best = (strings[cr.string_id], strings[sr.string_id], target_hits, dist)

        if best:
            client_id, secret_id, hits, dist = best
            self._log(f"  Client ID: {client_id}")
            self._log(f"  Secret ID: {secret_id}")
            self._log(f"  (target hits: {hits}, bytecode distance: {dist})")
            self._log(f"  Extracted in {time.time() - t0:.2f}s")
            return client_id, secret_id

        self._log("  Mobile credentials not found.")
        return None, None
