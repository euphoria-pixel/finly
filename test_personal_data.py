import unittest
from types import SimpleNamespace
from unittest.mock import patch

from main import remove_personal_data


class PersonalDataTests(unittest.TestCase):
    def clean_with_spans(self, text, spans=()):
        doc = SimpleNamespace(
            segment=lambda _: None,
            tag_ner=lambda _: None,
            spans=[SimpleNamespace(start=a, stop=b, type='PER') for a, b in spans],
        )
        with patch('main.Doc', return_value=doc):
            return remove_personal_data(text)

    def test_partial_ner_with_pdf_line_breaks(self):
        for separator in (' ', '\n', '\n\n', '\u00a0'):
            with self.subTest(separator=separator):
                text = 'Иванов Иван' + separator + 'Евгеньевич'
                self.assertEqual(self.clean_with_spans(text, [(0, 11)]), '[ФИО УДАЛЕНО]')

    def test_patronymics_without_ner(self):
        for name in ('Евгеньевич', 'ЕВГЕНЬЕВИЧ', 'евгеньевич', 'Евгеньевича',
                     'Сергеевичу', 'Андреевичем', 'Ильич', 'Ильинична',
                     'Ильиничной', 'Петровна', 'Петровны', 'Петровне', 'Петровну'):
            with self.subTest(name=name):
                self.assertEqual(self.clean_with_spans(name), '[ФИО УДАЛЕНО]')

    def test_overlapping_matches(self):
        text = 'Иванов Иван Сергеевич'
        self.assertEqual(self.clean_with_spans(text, [(0, len(text))]), '[ФИО УДАЛЕНО]')

    def test_initials_after_partial_ner(self):
        self.assertEqual(self.clean_with_spans('Иванов И. И.', [(0, 6)]), '[ФИО УДАЛЕНО]')

    def test_transaction_data_preserved(self):
        text = '15.08.2026\n-111.38 ₽\nОплата в PYATEROCHKA\nПеревод себе\n2065'
        self.assertEqual(self.clean_with_spans(text), text)

    def test_real_ner(self):
        self.assertEqual(remove_personal_data('Иванов Иван Евгеньевич'), '[ФИО УДАЛЕНО]')


if __name__ == '__main__':
    unittest.main()
