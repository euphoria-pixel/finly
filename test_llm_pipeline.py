import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from llm_pipeline import analyze_statement, compact_json, pack_statement, response_to_csv


DATA = {
    'd': ['28.02.2026'],
    't': [['Магазин, "товары"\nкасса', 'RUB', 'покупки']],
    'r': [[0, 0, '-141.5700'], [0, 0, '-141.5700'], [0, 0, '+2.00']],
}


def fake_client(content=None, finish='stop'):
    client = Mock()
    client.base_url = 'https://example.invalid/v1'
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(
            finish_reason=finish,
            message=SimpleNamespace(content=content or compact_json(DATA)),
        )],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=40),
    )
    return client


class PipelineTests(unittest.TestCase):
    def test_input_compression_is_reversible(self):
        text = ('Повторяющееся длинное описание операции\n12.34 RUB\n' * 40
                + 'Разовая операция\n')
        packed = pack_statement(text)
        self.assertLess(len(packed), len(text))
        data = json.loads(packed)
        restored = '\n'.join(
            data['dict'][int(line[1:])] if line.startswith('@') else line
            for line in data['text'].split('\n')
        )
        self.assertEqual(restored, text)

    def test_short_text_and_reference_collision_unchanged(self):
        for text in ('Короткая выписка\n', '@0\n' + 'Длинное описание' * 20):
            self.assertEqual(pack_statement(text), text)

    def test_csv_preserves_duplicates_quotes_newlines_and_amount_precision(self):
        rows = list(csv.reader(io.StringIO(response_to_csv(compact_json(DATA)))))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[1], ['28.02.2026', DATA['t'][0][0], '-141.5700', 'RUB', 'покупки'])
        self.assertEqual(rows[1], rows[2])
        self.assertEqual(rows[3][2], '+2.00')

    def test_invalid_responses_rejected(self):
        for content in ('{}', 'not json', compact_json({**DATA, 'r': [[-1, 0, '1']]}),
                        compact_json({**DATA, 'r': [[0, True, '1']]}),
                        compact_json({**DATA, 'r': [[0, 9, '1']]}),
                        compact_json({**DATA, 'r': [[0, 0, True]]})):
            with self.subTest(content=content), self.assertRaises(ValueError):
                response_to_csv(content)

    def test_numeric_amounts_keep_decimal_precision(self):
        content = ('{"d":["28.02.2026"],"t":[["Оплата","RUB","покупки"]],'
                   '"r":[[0,0,-141.5700],[0,0,9007199254740993.01],'
                   '[0,0,25],[0,0,1.20e2]]}')
        rows = list(csv.reader(io.StringIO(response_to_csv(content))))
        self.assertEqual([row[2] for row in rows[1:]],
                         ['-141.5700', '9007199254740993.01', '25', '120'])

    def test_formatted_amounts(self):
        for value, expected in [('−1 234,50', '-1234.50'),
                                ('+1\u00a0234.500', '+1234.500'),
                                (' 1\u202f234\u202f567,89 ', '1234567.89'),
                                ('0', '0'), ('', '')]:
            with self.subTest(value=value):
                content = compact_json({**DATA, 'r': [[0, 0, value]]})
                rows = list(csv.reader(io.StringIO(response_to_csv(content))))
                self.assertEqual(rows[1][2], expected)

    def test_ambiguous_amounts_rejected_with_row_number(self):
        for value in ('12 34', '1,234.56', 'NaN', '10 RUB', None, False):
            content = compact_json({**DATA, 'r': [[0, 0, value]]})
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, '№1'):
                response_to_csv(content)
        for value in ('NaN', 'Infinity', '-Infinity'):
            content = compact_json(DATA).replace('"-141.5700"', value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                response_to_csv(content)

    def test_cache_and_invalidation(self):
        with TemporaryDirectory() as directory:
            client = fake_client()
            first, stats = analyze_statement(client, 'исходный текст', cache_dir=directory)
            self.assertEqual(stats['completion_tokens'], 40)
            second, stats = analyze_statement(client, 'исходный текст', cache_dir=directory)
            self.assertEqual(first, second)
            self.assertTrue(stats['cache_hit'])
            self.assertEqual(stats['prompt_tokens'], 0)
            self.assertEqual(client.chat.completions.create.call_count, 1)
            analyze_statement(client, 'другой текст', cache_dir=directory)
            analyze_statement(client, 'исходный текст', model='other', cache_dir=directory)
            client.base_url = 'https://other.invalid/v1'
            analyze_statement(client, 'исходный текст', cache_dir=directory)
            self.assertEqual(client.chat.completions.create.call_count, 4)

    def test_incomplete_or_invalid_response_never_cached(self):
        for client in (fake_client(content='{"d":', finish='length'), fake_client(content='{}')):
            with TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    analyze_statement(client, 'текст', cache_dir=directory)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_valid_response_accepted_regardless_of_finish_reason(self):
        for finish in ('length', 'STOP', None):
            with self.subTest(finish=finish):
                result, _ = analyze_statement(fake_client(finish=finish), 'текст', cache_dir=None)
                self.assertEqual(result, response_to_csv(compact_json(DATA)))

    def test_cache_disabled(self):
        client = fake_client()
        for _ in range(2):
            analyze_statement(client, 'текст', cache_dir=None)
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_corrupt_cache_regenerated(self):
        with TemporaryDirectory() as directory:
            client = fake_client()
            analyze_statement(client, 'текст', cache_dir=directory)
            next(Path(directory).iterdir()).write_text('{')
            _, stats = analyze_statement(client, 'текст', cache_dir=directory)
            self.assertFalse(stats['cache_hit'])
            self.assertEqual(client.chat.completions.create.call_count, 2)


if __name__ == '__main__':
    unittest.main()
