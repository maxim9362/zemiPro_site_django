"""Stage 02.1 catalog baseline, authored for Django (NOT a legacy import).

The twelve section names follow TECHNICAL_SPEC REQ-CAT-002.
The eight repair categories and 56 service slugs are retained unchanged.
New sample categories are a starting taxonomy, editable through admin; validate
names and translations with the owner before a public marketplace launch.
"""
SECTIONS = [
    [
        "repairs",
        "Ремонт и строительство",
        "Renovation and Construction",
        "שיפוצים ובנייה"
    ],
    [
        "home",
        "Уборка и дом",
        "Cleaning and Home",
        "ניקיון ובית"
    ],
    [
        "education",
        "Образование",
        "Education",
        "חינוך ולימודים"
    ],
    [
        "digital",
        "IT и цифровые услуги",
        "IT and Digital Services",
        "שירותי מחשוב ודיגיטל"
    ],
    [
        "beauty",
        "Красота и уход",
        "Beauty and Wellness",
        "יופי וטיפוח"
    ],
    [
        "sports",
        "Спорт и фитнес",
        "Sports and Fitness",
        "ספורט וכושר"
    ],
    [
        "transport",
        "Перевозки",
        "Transport and Moving",
        "הובלות ותחבורה"
    ],
    [
        "events",
        "Мероприятия",
        "Events",
        "אירועים"
    ],
    [
        "pets",
        "Услуги для животных",
        "Pet Services",
        "שירותים לבעלי חיים"
    ],
    [
        "cars",
        "Автомобили",
        "Automotive",
        "רכב"
    ],
    [
        "business",
        "Деловые и консультационные услуги",
        "Business and Consulting",
        "עסקים וייעוץ"
    ],
    [
        "other",
        "Прочие услуги",
        "Other Services",
        "שירותים נוספים"
    ]
]

REPAIR_CATEGORY_NAMES = [
    [
        "plumbing",
        "Plumbing",
        "אינסטלציה"
    ],
    [
        "electricity",
        "Electrical Services",
        "שירותי חשמל"
    ],
    [
        "air-conditioners",
        "Air Conditioning",
        "מיזוג אוויר"
    ],
    [
        "apartment-renovation",
        "Apartment Renovation",
        "שיפוץ דירות"
    ],
    [
        "handyman",
        "Handyman",
        "הנדימן"
    ],
    [
        "furniture-assembly",
        "Furniture Assembly",
        "הרכבת רהיטים"
    ],
    [
        "appliance-repair",
        "Appliance Repair",
        "תיקון מוצרי חשמל"
    ],
    [
        "emergency-repair",
        "Emergency Repairs",
        "תיקוני חירום"
    ]
]

REPAIR_SERVICE_NAMES = [
    [
        "leak-repair",
        "Leak repair",
        "תיקון נזילה"
    ],
    [
        "faucet-replacement",
        "Faucet replacement",
        "החלפת ברז"
    ],
    [
        "toilet-repair",
        "Toilet repair",
        "תיקון אסלה"
    ],
    [
        "drain-clogging",
        "Drain unclogging",
        "פתיחת סתימה"
    ],
    [
        "water-heater-installation",
        "Water heater installation",
        "התקנת דוד"
    ],
    [
        "pipe-replacement",
        "Pipe replacement",
        "החלפת צנרת"
    ],
    [
        "emergency-plumber",
        "Emergency plumber",
        "אינסטלטור דחוף"
    ],
    [
        "outlet-repair",
        "Outlet repair",
        "תיקון שקע חשמל"
    ],
    [
        "switch-replacement",
        "Switch replacement",
        "החלפת מתג"
    ],
    [
        "lighting-issues",
        "Lighting problems",
        "תקלות תאורה"
    ],
    [
        "electrical-panel",
        "Electrical panel service",
        "טיפול בלוח חשמל"
    ],
    [
        "short-circuit",
        "Short circuit repair",
        "תיקון קצר חשמלי"
    ],
    [
        "light-fixture-installation",
        "Light fixture installation",
        "התקנת גופי תאורה"
    ],
    [
        "emergency-electrician",
        "Emergency electrician",
        "חשמלאי דחוף"
    ],
    [
        "ac-repair",
        "Air conditioner repair",
        "תיקון מזגן"
    ],
    [
        "ac-installation",
        "Air conditioner installation",
        "התקנת מזגן"
    ],
    [
        "ac-cleaning",
        "Air conditioner cleaning",
        "ניקוי מזגן"
    ],
    [
        "ac-gas-refill",
        "Refrigerant refill",
        "מילוי גז למזגן"
    ],
    [
        "ac-not-cooling",
        "AC not cooling",
        "מזגן לא מקרר"
    ],
    [
        "ac-removal",
        "Air conditioner removal",
        "פירוק מזגן"
    ],
    [
        "ac-maintenance",
        "Air conditioner maintenance",
        "תחזוקת מזגן"
    ],
    [
        "room-renovation",
        "Room renovation",
        "שיפוץ חדר"
    ],
    [
        "kitchen-renovation",
        "Kitchen renovation",
        "שיפוץ מטבח"
    ],
    [
        "bathroom-renovation",
        "Bathroom renovation",
        "שיפוץ חדר רחצה"
    ],
    [
        "wall-painting",
        "Wall painting",
        "צביעת קירות"
    ],
    [
        "putty-work",
        "Wall plastering",
        "עבודות שפכטל"
    ],
    [
        "tiling",
        "Tiling",
        "עבודות ריצוף וחיפוי"
    ],
    [
        "minor-repair",
        "Minor repair",
        "תיקונים קטנים"
    ],
    [
        "shelf-installation",
        "Shelf installation",
        "התקנת מדף"
    ],
    [
        "door-repair",
        "Door repair",
        "תיקון דלת"
    ],
    [
        "curtain-rod-installation",
        "Curtain rod installation",
        "התקנת מוט וילון"
    ],
    [
        "minor-handyman",
        "Small home repair",
        "תיקונים קטנים בבית"
    ],
    [
        "handle-replacement",
        "Handle replacement",
        "החלפת ידית"
    ],
    [
        "mirror-installation",
        "Mirror installation",
        "התקנת מראה"
    ],
    [
        "general-handyman",
        "General handyman",
        "הנדימן לבית"
    ],
    [
        "wardrobe-assembly",
        "Wardrobe assembly",
        "הרכבת ארון"
    ],
    [
        "bed-assembly",
        "Bed assembly",
        "הרכבת מיטה"
    ],
    [
        "kitchen-assembly",
        "Kitchen assembly",
        "הרכבת מטבח"
    ],
    [
        "table-assembly",
        "Table assembly",
        "הרכבת שולחן"
    ],
    [
        "ikea-assembly",
        "IKEA furniture assembly",
        "הרכבת רהיטי איקאה"
    ],
    [
        "furniture-disassembly",
        "Furniture disassembly",
        "פירוק רהיטים"
    ],
    [
        "furniture-moving",
        "Furniture moving",
        "העברת רהיטים"
    ],
    [
        "washing-machine-repair",
        "Washing machine repair",
        "תיקון מכונת כביסה"
    ],
    [
        "dishwasher-repair",
        "Dishwasher repair",
        "תיקון מדיח כלים"
    ],
    [
        "oven-repair",
        "Oven repair",
        "תיקון תנור"
    ],
    [
        "refrigerator-repair",
        "Refrigerator repair",
        "תיקון מקרר"
    ],
    [
        "appliance-installation",
        "Appliance installation",
        "חיבור מכשירי חשמל"
    ],
    [
        "appliance-not-starting",
        "Appliance won't turn on",
        "מכשיר לא נדלק"
    ],
    [
        "appliance-diagnostics",
        "Appliance diagnostics",
        "אבחון תקלות במכשירי חשמל"
    ],
    [
        "emergency-leak",
        "Emergency leak repair",
        "טיפול דחוף בנזילה"
    ],
    [
        "power-outage",
        "Power outage assistance",
        "טיפול בהפסקת חשמל"
    ],
    [
        "emergency-lock-repair",
        "Emergency lock repair",
        "תיקון מנעול דחוף"
    ],
    [
        "emergency-handyman",
        "Emergency handyman",
        "הנדימן דחוף"
    ],
    [
        "night-emergency",
        "Night emergency service",
        "שירות חירום בלילה"
    ]
]

NEW_CATEGORIES = [
    {
        "section": "home",
        "slug": "house-cleaning",
        "ru": "Уборка помещений",
        "en": "Home Cleaning",
        "he": "ניקיון בתים",
        "mode": "onsite",
        "services": [
            [
                "regular-cleaning",
                "Регулярная уборка",
                "Regular cleaning",
                "ניקיון קבוע"
            ],
            [
                "deep-cleaning",
                "Генеральная уборка",
                "Deep cleaning",
                "ניקיון יסודי"
            ],
            [
                "move-out-cleaning",
                "Уборка после переезда",
                "Move-out cleaning",
                "ניקיון אחרי מעבר דירה"
            ]
        ]
    },
    {
        "section": "education",
        "slug": "tutoring",
        "ru": "Репетиторы",
        "en": "Tutoring",
        "he": "שיעורים פרטיים",
        "mode": "both",
        "services": [
            [
                "math-tutoring",
                "Математика",
                "Math tutoring",
                "שיעורים פרטיים במתמטיקה"
            ],
            [
                "language-tutoring",
                "Иностранные языки",
                "Language tutoring",
                "שיעורי שפות"
            ],
            [
                "exam-preparation",
                "Подготовка к экзаменам",
                "Exam preparation",
                "הכנה למבחנים"
            ]
        ]
    },
    {
        "section": "digital",
        "slug": "website-development",
        "ru": "Разработка сайтов",
        "en": "Website Development",
        "he": "פיתוח אתרים",
        "mode": "online",
        "services": [
            [
                "landing-page",
                "Лендинг",
                "Landing page",
                "דף נחיתה"
            ],
            [
                "business-website",
                "Сайт компании",
                "Business website",
                "אתר לעסק"
            ],
            [
                "website-maintenance",
                "Поддержка сайта",
                "Website maintenance",
                "תחזוקת אתרים"
            ]
        ]
    },
    {
        "section": "beauty",
        "slug": "hair-services",
        "ru": "Парикмахерские услуги",
        "en": "Hair Services",
        "he": "שירותי שיער",
        "mode": "onsite",
        "services": [
            [
                "haircut",
                "Стрижка",
                "Haircut",
                "תספורת"
            ],
            [
                "hair-coloring",
                "Окрашивание волос",
                "Hair coloring",
                "צביעת שיער"
            ],
            [
                "hair-styling",
                "Укладка волос",
                "Hair styling",
                "עיצוב שיער"
            ]
        ]
    },
    {
        "section": "sports",
        "slug": "personal-training",
        "ru": "Персональные тренировки",
        "en": "Personal Training",
        "he": "אימון אישי",
        "mode": "both",
        "services": [
            [
                "fitness-coaching",
                "Фитнес-тренировки",
                "Fitness coaching",
                "אימון כושר"
            ],
            [
                "yoga-training",
                "Йога",
                "Yoga training",
                "אימון יוגה"
            ],
            [
                "running-coaching",
                "Беговые тренировки",
                "Running coaching",
                "אימון ריצה"
            ]
        ]
    },
    {
        "section": "transport",
        "slug": "moving-services",
        "ru": "Квартирные переезды",
        "en": "Moving Services",
        "he": "שירותי הובלה",
        "mode": "onsite",
        "services": [
            [
                "apartment-moving",
                "Переезд квартиры",
                "Apartment moving",
                "הובלת דירה"
            ],
            [
                "small-item-moving",
                "Перевозка небольших грузов",
                "Small item moving",
                "הובלת פריטים קטנים"
            ],
            [
                "packing-help",
                "Помощь с упаковкой",
                "Packing assistance",
                "עזרה באריזה"
            ]
        ]
    },
    {
        "section": "events",
        "slug": "event-services",
        "ru": "Услуги для мероприятий",
        "en": "Event Services",
        "he": "שירותים לאירועים",
        "mode": "onsite",
        "services": [
            [
                "event-photography",
                "Фотосъёмка мероприятий",
                "Event photography",
                "צילום אירועים"
            ],
            [
                "event-decor",
                "Оформление мероприятия",
                "Event decoration",
                "עיצוב אירועים"
            ],
            [
                "event-planning",
                "Организация мероприятий",
                "Event planning",
                "תכנון אירועים"
            ]
        ]
    },
    {
        "section": "pets",
        "slug": "pet-care",
        "ru": "Уход за животными",
        "en": "Pet Care",
        "he": "טיפול בחיות מחמד",
        "mode": "onsite",
        "services": [
            [
                "dog-walking",
                "Выгул собак",
                "Dog walking",
                "הוצאת כלבים לטיול"
            ],
            [
                "pet-sitting",
                "Присмотр за питомцами",
                "Pet sitting",
                "שמירה על חיות מחמד"
            ],
            [
                "pet-grooming",
                "Груминг",
                "Pet grooming",
                "טיפוח חיות מחמד"
            ]
        ]
    },
    {
        "section": "cars",
        "slug": "car-services",
        "ru": "Автоуслуги",
        "en": "Car Services",
        "he": "שירותי רכב",
        "mode": "onsite",
        "services": [
            [
                "car-wash",
                "Мойка автомобиля",
                "Car wash",
                "שטיפת רכב"
            ],
            [
                "car-detailing",
                "Детейлинг",
                "Car detailing",
                "דיטיילינג לרכב"
            ],
            [
                "vehicle-inspection-help",
                "Помощь с осмотром автомобиля",
                "Vehicle inspection assistance",
                "סיוע בבדיקת רכב"
            ]
        ]
    },
    {
        "section": "business",
        "slug": "business-consulting",
        "ru": "Консультации для бизнеса",
        "en": "Business Consulting",
        "he": "ייעוץ עסקי",
        "mode": "both",
        "services": [
            [
                "business-planning",
                "Бизнес-планирование",
                "Business planning",
                "תכנון עסקי"
            ],
            [
                "bookkeeping-help",
                "Помощь с учётом",
                "Bookkeeping assistance",
                "סיוע בניהול חשבונות"
            ],
            [
                "document-preparation",
                "Подготовка документов",
                "Document preparation",
                "הכנת מסמכים"
            ]
        ]
    },
    {
        "section": "other",
        "slug": "other-services",
        "ru": "Другие услуги",
        "en": "Other Services",
        "he": "שירותים נוספים",
        "mode": "both",
        "services": [
            [
                "general-assistance",
                "Разовая помощь",
                "General assistance",
                "עזרה חד פעמית"
            ],
            [
                "custom-request",
                "Индивидуальный запрос",
                "Custom service request",
                "בקשת שירות אישית"
            ]
        ]
    }
]
