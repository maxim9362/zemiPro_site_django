"""Stage 02.2 curated 25-city pilot subset and six CBS statistical districts.

This is NOT the complete registry of Israeli municipalities/localities.
Existing Django city slugs and Russian names are retained verbatim.
Geographic groupings are statistical only; service areas remain user-selected.
Source for administrative structure: CBS (https://census.cbs.gov.il/en,
https://data.gov.il/he/datasets/lamas/localities-in-israel/d47a54ff-87f0-44b3-b33a-f284c0c38e5a).
Validate assignments/transliterations before scaling beyond the pilot subset.
"""

DISTRICTS = [
    [
        "jerusalem",
        "Иерусалимский",
        "Jerusalem",
        "ירושלים"
    ],
    [
        "north",
        "Северный",
        "Northern",
        "הצפון"
    ],
    [
        "haifa",
        "Хайфский",
        "Haifa",
        "חיפה"
    ],
    [
        "central",
        "Центральный",
        "Central",
        "המרכז"
    ],
    [
        "tel-aviv",
        "Тель-Авивский",
        "Tel Aviv",
        "תל אביב"
    ],
    [
        "south",
        "Южный",
        "Southern",
        "הדרום"
    ]
]

CITIES = [
    [
        "ashdod",
        "Ашдод",
        "Ashdod",
        "אשדוד",
        "south"
    ],
    [
        "ashkelon",
        "Ашкелон",
        "Ashkelon",
        "אשקלון",
        "south"
    ],
    [
        "tel-aviv",
        "Тель-Авив",
        "Tel Aviv-Yafo",
        "תל אביב-יפו",
        "tel-aviv"
    ],
    [
        "bat-yam",
        "Бат-Ям",
        "Bat Yam",
        "בת ים",
        "tel-aviv"
    ],
    [
        "holon",
        "Холон",
        "Holon",
        "חולון",
        "tel-aviv"
    ],
    [
        "rishon-lezion",
        "Ришон-ле-Цион",
        "Rishon LeZion",
        "ראשון לציון",
        "central"
    ],
    [
        "rehovot",
        "Реховот",
        "Rehovot",
        "רחובות",
        "central"
    ],
    [
        "yavne",
        "Явне",
        "Yavne",
        "יבנה",
        "central"
    ],
    [
        "gan-yavne",
        "Ган-Явне",
        "Gan Yavne",
        "גן יבנה",
        "central"
    ],
    [
        "kiryat-malakhi",
        "Кирьят-Малахи",
        "Kiryat Malakhi",
        "קריית מלאכי",
        "south"
    ],
    [
        "kiryat-gat",
        "Кирьят-Гат",
        "Kiryat Gat",
        "קריית גת",
        "south"
    ],
    [
        "sderot",
        "Сдерот",
        "Sderot",
        "שדרות",
        "south"
    ],
    [
        "netivot",
        "Нетивот",
        "Netivot",
        "נתיבות",
        "south"
    ],
    [
        "ofakim",
        "Офаким",
        "Ofakim",
        "אופקים",
        "south"
    ],
    [
        "beer-sheva",
        "Беэр-Шева",
        "Be'er Sheva",
        "באר שבע",
        "south"
    ],
    [
        "jerusalem",
        "Иерусалим",
        "Jerusalem",
        "ירושלים",
        "jerusalem"
    ],
    [
        "haifa",
        "Хайфа",
        "Haifa",
        "חיפה",
        "haifa"
    ],
    [
        "netanya",
        "Нетания",
        "Netanya",
        "נתניה",
        "central"
    ],
    [
        "petah-tikva",
        "Петах-Тиква",
        "Petah Tikva",
        "פתח תקווה",
        "central"
    ],
    [
        "ramat-gan",
        "Рамат-Ган",
        "Ramat Gan",
        "רמת גן",
        "tel-aviv"
    ],
    [
        "bnei-brak",
        "Бней-Брак",
        "Bnei Brak",
        "בני ברק",
        "tel-aviv"
    ],
    [
        "herzliya",
        "Герцлия",
        "Herzliya",
        "הרצליה",
        "tel-aviv"
    ],
    [
        "raanana",
        "Раанана",
        "Ra'anana",
        "רעננה",
        "central"
    ],
    [
        "kfar-saba",
        "Кфар-Саба",
        "Kfar Saba",
        "כפר סבא",
        "central"
    ],
    [
        "modiin",
        "Модиин",
        "Modi'in-Maccabim-Re'ut",
        "מודיעין-מכבים-רעות",
        "central"
    ]
]

ALIASES = [
    [
        "tel-aviv-yafo",
        "tel-aviv"
    ],
    [
        "petah-tiqwa",
        "petah-tikva"
    ],
    [
        "beersheba",
        "beer-sheva"
    ],
    [
        "rishon-leziyyon",
        "rishon-lezion"
    ]
]
