"""Which uploaded archive is which card, and how each one is built.

`src` is the folder under assets_raw/ (the zip's own name). Identified by
rendering every archive to a contact sheet -- see tools/contact_sheet.py.
"""

ROSTER = {
    "mega_knight_blue": {
        "src": "34b7438e-8f07-4663-9cc0-26891da8e570",
        "label": "Мега-Найт",
        "archetype": "mega",
        "clips": ["idle", "walk", "attack", "hit", "die", "jump", "smash"],
        "height": 2.6,
    },
    "mega_knight_red": {
        "src": "615a648e-c0e0-476d-8254-da8b80ef10eb",
        "label": "Мега-Найт",
        "archetype": "mega",
        "clips": ["idle", "walk", "attack", "hit", "die", "jump", "smash"],
        "height": 2.6,
    },
    "mega_knight_trump": {
        "src": "9f357f87-80b9-4f04-bab5-b022fcc0f618",
        "label": "Мега-Найт Трамп",
        "archetype": "mega",
        "clips": ["idle", "walk", "attack", "hit", "die", "jump", "smash"],
        "height": 2.8,
    },
    "barbarian": {
        "src": "292893b0-e054-49a7-91b6-f555940c3a0c",
        "label": "Варвар",
        "archetype": "biped",
        "clips": ["idle", "walk", "attack", "hit", "die"],
        "height": 1.9,
    },
    "archer_blue": {
        "src": "9e82ac55-a50a-42c4-bd8f-2f351c8fe006",
        "label": "Лучница",
        "archetype": "biped",
        "clips": ["idle", "walk", "shoot", "hit", "die"],
        "height": 1.6,
    },
    "archer_red": {
        "src": "e092ce7c-aa6b-46d0-b388-781c6d2a7689",
        "label": "Принцесса",
        "archetype": "biped",
        "clips": ["idle", "walk", "shoot", "hit", "die"],
        "height": 1.6,
    },
    "skeleton_archer": {
        "src": "1c638de5-eb5d-4048-b579-0c187ce1a633",
        "label": "Скелет-лучник",
        "archetype": "biped",
        "clips": ["idle", "walk", "shoot", "hit", "die"],
        "height": 1.45,
    },
    "hog_rider": {
        "src": "af37ae7e-ac6d-4065-94a5-4afaa8f87c1c",
        "label": "Всадник на кабане",
        "archetype": "rider",
        "clips": ["idle", "walk", "attack", "hit", "die"],
        "height": 2.0,
    },
    "baby_dragon": {
        "src": "c5bc0717-fa3c-458b-875d-e0ce7bcb45e6",
        "label": "Дракончик",
        "archetype": "dragon",
        "clips": ["idle", "walk", "shoot", "hit", "die"],
        "height": 1.9,
        "fly": 1.7,
    },
    "king_blue": {
        "src": "e4574fac-2951-4a85-b65c-f27bba2a3b36",
        "label": "Король",
        "archetype": "biped",
        "clips": ["idle", "shoot", "hit", "die"],
        "height": 2.1,
    },
    "king_red": {
        "src": "f433705e-59d4-48b1-8dc3-4ef1f58bd88d",
        "label": "Король",
        "archetype": "biped",
        "clips": ["idle", "shoot", "hit", "die"],
        "height": 2.1,
    },
}
