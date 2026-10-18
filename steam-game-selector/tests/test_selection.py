import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.select_games import (
    add_batch, allocate_unique, is_aaa_proxy, parse_owners,
    rank_categories, valid_game,
)
from src.steamspy_client import SteamSpyClient


class SelectionTest(unittest.TestCase):
    def test_owners_range(self):
        self.assertEqual(parse_owners('1,000,000 .. 2,000,000'), (1000000, 2000000))
        self.assertEqual(parse_owners(None), (0, 0))

    def test_or_union_and_dedup(self):
        from collections import defaultdict
        reg = {}
        members = defaultdict(lambda: defaultdict(set))
        one = {'1': {'appid': 1, 'name': 'Jogo A', 'owners': '100 .. 200'},
               '2': {'appid': 2, 'name': 'Jogo B', 'owners': '200 .. 300'}}
        two = {'1': {'appid': 1, 'name': 'Jogo A', 'ccu': 44},
               '3': {'appid': 3, 'name': 'Jogo C', 'owners': '300 .. 400'}}
        add_batch(reg, members, one, 'competitive', 'tag:FPS', set())
        add_batch(reg, members, two, 'competitive', 'tag:PvP', set())
        self.assertEqual(set(members['competitive']), {1, 2, 3})
        self.assertEqual(members['competitive'][1], {'tag:FPS', 'tag:PvP'})

    def test_aaa_proxy_is_conservative(self):
        cfg = {'publisher_allowlist': ['EA', 'Ubisoft', 'SEGA'], 'require_paid': True}
        self.assertTrue(is_aaa_proxy({'publisher': 'Ubisoft', 'price': '3999'}, cfg))
        self.assertFalse(is_aaa_proxy({'publisher': 'Dream Studios', 'price': '3999'}, cfg))
        self.assertFalse(is_aaa_proxy({'publisher': 'SEGA', 'price': '0'}, cfg))

    def test_game_filter(self):
        self.assertFalse(valid_game(123, {'name': 'Example OST Soundtrack'}, set()))
        self.assertFalse(valid_game(123, {'name': 'Example'}, {123}))
        self.assertTrue(valid_game(123, {'name': 'Example'}, set()))

    def test_unique_allocation(self):
        cats = [{'id': 'indie'}, {'id': 'competitive'}]
        ranks = {'indie': [1, 2, 3], 'competitive': [1, 2, 4, 5]}
        selected, order = allocate_unique(cats, ranks, 2)
        self.assertEqual(order[0], 'indie')
        self.assertEqual([aid for aid, _ in selected['indie']], [1, 2])
        self.assertEqual([aid for aid, _ in selected['competitive']], [4, 5])

    def test_cache_no_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = SteamSpyClient(Path(tmp))
            path = client._cache_path({'request': 'tag', 'tag': 'FPS'})
            path.write_text(json.dumps({'42': {'appid': 42, 'name': 'Example'}}), encoding='utf-8')
            with patch.object(client.session, 'get', side_effect=AssertionError('HTTP not expected')):
                data = client.get(request='tag', tag='FPS')
            self.assertIn('42', data)
            self.assertEqual(client.cache_hits, 1)


    def test_end_to_end_offline_15_unique_games(self):
        from src import select_games as mod
        import sys
        from unittest.mock import MagicMock
        root = Path(__file__).resolve().parents[1]
        def mk(prefix, number, publisher='Small Studio', price='1599'):
            return {str(prefix+i): {
                'appid': prefix+i, 'name': f'Jogo {prefix+i}',
                'owners': f'{(number-i)*100000:,} .. {(number-i+1)*100000:,}',
                'ccu': number-i, 'publisher': publisher, 'price': price,
            } for i in range(4)}
        def mock_get(**kw):
            if kw['request'] == 'all':
                return mk(400, 100, publisher='Ubisoft')
            if kw['request'] == 'tag' and kw.get('tag') == 'FPS':
                return mk(1, 100)
            if kw['request'] == 'tag' and kw.get('tag') == 'Indie':
                return mk(100, 100)
            if kw['request'] == 'tag' and kw.get('tag') == 'Strategy':
                return mk(200, 100)
            if kw['request'] == 'tag' and kw.get('tag') == 'Survival':
                return mk(300, 100)
            return {}
        fake = MagicMock()
        fake.get.side_effect = mock_get
        fake.calls = 15
        fake.cache_hits = 0
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'selected'
            with patch.object(mod, 'SteamSpyClient', return_value=fake), patch.object(sys, 'argv', [
                'select_games', '--per-category', '3', '--catalog-pages', '1',
                '--config', str(root/'config/categories.json'),
                '--exclusions', str(root/'config/exclusions.csv'),
                '--out', str(output), '--cache', str(Path(tmp)/'cache'), '--strict',
            ]):
                self.assertEqual(mod.main(), 0)
            with (output/'games_15.csv').open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 15)
            self.assertEqual(len(set(row['appid'] for row in rows)), 15)
            self.assertEqual(set(row['category'] for row in rows), {
                'competitive', 'aaa', 'indie', 'strategy_sim', 'survival_coop'
            })


if __name__ == '__main__':
    unittest.main()
