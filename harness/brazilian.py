"""A beginner Brazilian Portuguese curriculum.

Ordered roughly by frequency/difficulty (the Progress drive introduces unseen
items easiest-first). Includes two confusable pairs (ser/estar, comer/beber)
to exercise INV-INTERLEAVE, several multi-word chunks taught as single units,
and a few phonologically tricky items (nasal vowels, accents) that route audio.
"""
from .model import Item


def brazilian_curriculum() -> list:
    return [
        Item("oi", "oi", "vocab", 0.08, gloss="hi (informal)"),
        Item("sim", "sim", "vocab", 0.10, gloss="yes", is_phonological=True,
             hint="nasal 'i'"),
        Item("nao", "não", "vocab", 0.12, gloss="no", is_phonological=True,
             hint="nasal 'ão'"),
        Item("tchau", "tchau", "vocab", 0.13, gloss="bye"),
        Item("eu", "eu", "vocab", 0.15, gloss="I"),
        Item("obrigado", "obrigado", "vocab", 0.18, gloss="thank you",
             hint="a man says 'obrigado', a woman says 'obrigada' (agrees with speaker)"),
        Item("agua", "água", "vocab", 0.20, gloss="water", is_phonological=True,
             hint="stress on first syllable: Á-gua"),
        Item("cafe", "café", "vocab", 0.20, gloss="coffee", is_phonological=True,
             hint="stress on final é"),
        Item("por_favor", "por favor", "chunk", 0.22, gloss="please"),
        Item("voce", "você", "vocab", 0.25, gloss="you (informal in Brazil)"),
        Item("bom_dia", "bom dia", "chunk", 0.28, gloss="good morning"),
        Item("de_nada", "de nada", "chunk", 0.30, gloss="you're welcome"),
        Item("com_licenca", "com licença", "chunk", 0.34, gloss="excuse me"),
        Item("quero", "quero", "vocab", 0.38, gloss="I want",
             hint="from 'querer'; 'quero água' = I want water"),
        Item("comer", "comer", "vocab", 0.40, gloss="to eat", confusable=("beber",)),
        Item("beber", "beber", "vocab", 0.42, gloss="to drink", confusable=("comer",)),
        Item("eu_gosto_de", "eu gosto de", "chunk", 0.46, gloss="I like",
             hint="literally 'I please of'; 'eu gosto de café' = I like coffee"),
        Item("falar", "falar", "vocab", 0.48, gloss="to speak"),
        Item("ser", "ser", "grammar", 0.55, gloss="to be (permanent/essential)",
             confusable=("estar",), hint="identity, origin, traits: 'eu sou' = I am"),
        Item("estar", "estar", "grammar", 0.58, gloss="to be (temporary/state)",
             confusable=("ser",), hint="states, location: 'eu estou' = I am (right now)"),
    ]
