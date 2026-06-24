"""A beginner Russian curriculum — for QA by a native speaker (judge the output
quality directly), parallel in structure to brazilian.py. Cyrillic lemmas, a
confusable pair (есть/пить), chunks, ordered easiest-first.
"""
from .model import Item


def russian_curriculum() -> list:
    return [
        Item("privet", "привет", "vocab", 0.10, gloss="hi (informal)"),
        Item("da", "да", "vocab", 0.08, gloss="yes"),
        Item("net", "нет", "vocab", 0.10, gloss="no"),
        Item("poka", "пока", "vocab", 0.13, gloss="bye (informal)"),
        Item("ya", "я", "vocab", 0.12, gloss="I"),
        Item("spasibo", "спасибо", "vocab", 0.18, gloss="thank you"),
        Item("ty", "ты", "vocab", 0.20, gloss="you (informal)"),
        Item("voda", "вода", "vocab", 0.22, gloss="water", is_phonological=True,
             hint="stress on the last syllable: vo-DA"),
        Item("kofe", "кофе", "vocab", 0.20, gloss="coffee"),
        Item("pozhaluysta", "пожалуйста", "vocab", 0.30, gloss="please / you're welcome",
             hint="also the reply to 'спасибо'"),
        Item("ochen", "очень", "vocab", 0.32, gloss="very"),
        Item("khorosho", "хорошо", "vocab", 0.30, gloss="good / okay",
             is_phonological=True, hint="unstressed o's sound like 'a': kha-ra-SHO"),
        Item("dobroe_utro", "доброе утро", "chunk", 0.34, gloss="good morning"),
        Item("izvinite", "извините", "chunk", 0.36, gloss="excuse me / sorry"),
        Item("khochu", "хочу", "vocab", 0.40, gloss="I want", hint="from хотеть"),
        Item("est", "есть", "vocab", 0.44, gloss="to eat", confusable=("pit",)),
        Item("pit", "пить", "vocab", 0.44, gloss="to drink", confusable=("est",)),
        Item("lyubit", "любить", "vocab", 0.48, gloss="to like / love"),
        Item("govorit", "говорить", "vocab", 0.50, gloss="to speak"),
        Item("byt", "быть", "grammar", 0.55, gloss="to be",
             hint="usually dropped in the present: 'я студент' = I (am a) student"),
    ]
