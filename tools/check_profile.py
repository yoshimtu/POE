"""Offline update report. Never modifies or enables a memory profile."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct


SIGNATURES = {
    "file_root_rva": ("89 ?? ?? ?? ?? ?? ?? 8B ?? ?? 8B ?? ?? ?? ?? 8B ?? ?? ?? 0F 28 ?? ?? ?? ?? 83 ?? ?? ?? ?? ?? ?? C3", 2, 6),
    "area_counter_rva": ("8B ?? ?? ?? ?? ?? ?? 8B ?? FF ?? ?? ?? ?? ?? E8 ?? ?? ?? ?? FF ?? ?? ?? ?? ?? ?? 8B", 22, 26),
}


def report(executable, profile):
    data = executable.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if data[:2] != b'MZ' or data[pe:pe + 4] != b'PE\0\0':
        raise ValueError('Not a PE executable')
    machine, count = struct.unpack_from('<HH', data, pe + 4)
    optional_size = struct.unpack_from('<H', data, pe + 20)[0]
    optional = pe + 24
    if machine != 0x8664 or struct.unpack_from('<H', data, optional)[0] != 0x20b:
        raise ValueError('Expected x64 PE')
    image_size = struct.unpack_from('<I', data, optional + 56)[0]
    sections = []
    for index in range(count):
        start = optional + optional_size + 40 * index
        virtual_size, rva, size, raw = struct.unpack_from('<IIII', data, start + 8)
        flags = struct.unpack_from('<I', data, start + 36)[0]
        if flags & 0x20000000:
            sections.append((rva, raw, size))
    result = {'exe_sha256': hashlib.sha256(data).hexdigest(), 'image_size': image_size,
              'matches_existing_hash': hashlib.sha256(data).hexdigest() == profile.get('exe_sha256'),
              'signatures': {}, 'validated': False,
              'note': 'Root candidates only. Field layouts, new hash and live behavior require separate validation.'}
    for name, (pattern, displacement, instruction_end) in SIGNATURES.items():
        expression = b''.join(b'.' if token == '??' else re.escape(bytes.fromhex(token)) for token in pattern.split())
        matches = []
        for rva, raw, size in sections:
            for match in re.finditer(expression, data[raw:raw + size], re.S):
                target = rva + match.start() + instruction_end + struct.unpack_from('<i', data, raw + match.start() + displacement)[0]
                if 0 <= target < image_size:
                    matches.append(target)
        result['signatures'][name] = {'count': len(matches), 'candidate_rvas': [hex(x) for x in matches],
                                      'matches_profile': len(matches) == 1 and matches[0] == profile['offsets'].get(name)}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--profile', type=Path, default=Path('profiles/steam-25113903.read-only.json'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    value = report(args.executable, json.loads(args.profile.read_text()))
    rendered = json.dumps(value, indent=2)
    if args.output:
        args.output.write_text(rendered + '\n')
    print(rendered)
