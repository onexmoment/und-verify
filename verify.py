#!/usr/bin/env python3
"""Provably Fair верификатор для Underrolling Roulette.

Алгоритм:
  1. Проверяет SHA-256(seed) == commit_hash
  2. Вычисляет roll = SHA-256(seed || round_id_be8 || bet_id_bytes...)
  3. point = int(roll[:8]) % total_effective
  4. Weighted selection → победитель

Использование:
  python verify.py --api https://api.dev-underrolling.io --round 15
  python verify.py --file round_15.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any


def verify_round(data: dict[str, Any]) -> bool:
    """Верифицировать результат раунда."""
    round_id: int = data['round_id']
    commit_hash: str = data['commit_hash']
    seed_hex: str = data['seed_hex']
    roll_value_expected: str = data['roll_value']
    winner_bet_id: str = data['winner_bet_id']
    bets: list[dict[str, Any]] = data['bets']

    seed = bytes.fromhex(seed_hex)

    print(f'=== Раунд #{round_id} ===')
    print(f'Seed:        {seed_hex}')
    print(f'Commit hash: {commit_hash}')
    print(f'Ставок:      {len(bets)}')
    print()

    # --- 1. Проверка commit_hash ---
    computed_hash = hashlib.sha256(seed).hexdigest()
    hash_ok = computed_hash == commit_hash
    print(f'[1] SHA-256(seed) = {computed_hash}')
    print(f'    commit_hash   = {commit_hash}')
    print(f'    Результат:    {"✅ совпадает" if hash_ok else "❌ НЕ СОВПАДАЕТ"}')
    print()

    if not hash_ok:
        print('ВЕРИФИКАЦИЯ ПРОВАЛЕНА: commit_hash не соответствует seed')
        return False

    # --- 2. Вычисление roll ---
    sorted_bets = sorted(bets, key=lambda b: b['bet_id'])

    roll_input = bytearray(seed)
    roll_input += round_id.to_bytes(8, 'big')
    for bet in sorted_bets:
        roll_input += uuid.UUID(bet['bet_id']).bytes

    roll_hash = hashlib.sha256(roll_input).digest()
    roll_value = int.from_bytes(roll_hash[:8], 'big')
    roll_hex = roll_hash[:8].hex()

    roll_ok = roll_hex == roll_value_expected
    print(f'[2] Roll hash (first 8 bytes): {roll_hex}')
    print(f'    Ожидаемый:                 {roll_value_expected}')
    print(f'    Результат: {"✅ совпадает" if roll_ok else "❌ НЕ СОВПАДАЕТ"}')
    print()

    # --- 3. Weighted selection ---
    total_effective = sum(b['effective_nanoton'] for b in sorted_bets)
    point = roll_value % total_effective

    print(f'[3] Roll value:     {roll_value}')
    print(f'    Total effective: {total_effective} nanoTON')
    print(f'    Point:          {point}')
    print()

    cumulative = 0
    computed_winner = None
    print('    Ставки (отсортированы по UUID):')
    for bet in sorted_bets:
        eff = bet['effective_nanoton']
        prev_cum = cumulative
        cumulative += eff
        marker = ''
        if computed_winner is None and point < cumulative:
            computed_winner = bet['bet_id']
            marker = ' ◀ ПОБЕДИТЕЛЬ'
        print(
            f'      {bet["bet_id"]}  '
            f'effective={eff:>15}  '
            f'range=[{prev_cum}, {cumulative}){marker}'
        )
    print()

    if computed_winner is None:
        computed_winner = sorted_bets[-1]['bet_id']

    winner_ok = computed_winner == winner_bet_id
    print(f'[4] Вычисленный победитель: {computed_winner}')
    print(f'    Заявленный победитель:  {winner_bet_id}')
    print(f'    Результат: {"✅ совпадает" if winner_ok else "❌ НЕ СОВПАДАЕТ"}')
    print()

    all_ok = hash_ok and roll_ok and winner_ok
    if all_ok:
        print('✅ ВЕРИФИКАЦИЯ ПРОЙДЕНА: результат честный')
    else:
        print('❌ ВЕРИФИКАЦИЯ ПРОВАЛЕНА')

    return all_ok


def fetch_from_api(api_url: str, round_id: int) -> dict[str, Any]:
    """Загрузить данные верификации из API."""
    import urllib.request

    url = f'{api_url.rstrip("/")}/api/v1/offchain/rounds/{round_id}/fairness'
    print(f'Загрузка: {url}')
    print()

    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Provably Fair верификатор Underrolling Roulette',
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--api',
        help='Base URL API (например https://api.dev-underrolling.io)',
    )
    group.add_argument(
        '--file',
        help='JSON-файл с данными верификации',
    )
    parser.add_argument(
        '--round',
        type=int,
        help='ID раунда (обязателен при --api)',
    )
    args = parser.parse_args()

    if args.api:
        if args.round is None:
            parser.error('--round обязателен при использовании --api')
        data = fetch_from_api(args.api, args.round)
    else:
        data = json.loads(Path(args.file).read_text(encoding='utf-8'))

    ok = verify_round(data)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
