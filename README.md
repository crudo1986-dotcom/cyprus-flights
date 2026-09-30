# cyprus-flights

מנוע רקע שמחפש טיסות זולות לקפריסין מתל אביב (TLV) או חיפה (HFA) ללרנקה (LCA) ומחזיר **רק הצעות עם 4 מקומות יחד על אותה טיסה**.
Background watcher for cheap flights from Tel Aviv or Haifa to Larnaca; only offers that seat all 4 passengers on the same flight.

## איך זה עובד / How it works
- **4 ביחד:** כל חיפוש נשלח עם `adults=4`, ובנוסף כל הצעה נבדקת (`numberOfBookableSeats >= 4` ו-4 נוסעים בתמחור). הצעה שלא מתאימה נזרקת.
- **בלי בזבוז:** Python בלבד (stdlib), בלי LLM בלולאה. קריאת API אחת לכל (מוצא, יעד, תאריך), תקרת קריאות יומית קשיחה, טוקן OAuth נשמר ונעשה בו שימוש חוזר עד פקיעה, רענון תדיר יותר רק לטיסות קרובות, backoff על כשלים, ועצירה על שגיאות auth/quota (401/403/429).
- **התראות:** רק כשהמחיר מתחת לסף (`max_price_per_person`) או ירד ≥5% מהמחיר הכי טוב שנצפה; בלי כפילויות. נכתב ל-`alerts.jsonl` ואופציונלית ל-webhook (ntfy/Slack וכו').

## שימוש / Usage
```
cp config.example.json config.json      # ערוך תאריכים/סף מחיר
export AMADEUS_API_KEY=... AMADEUS_API_SECRET=...   # חינם: developers.amadeus.com
python -m flightwatch plan              # כמה חיפושים בסריקה מלאה
python -m flightwatch run               # רץ ברקע (nohup / systemd / tmux)
python -m flightwatch best              # המחירים הזולים שנמצאו
python -m unittest discover -s tests
```
לבדיקה בלי API: `"provider": "mock"`.

טיפ: `python -m flightwatch plan` מראה את מספר החיפושים; אם גדול מ-`daily_call_budget`, צמצם טווח תאריכים או הגדל את `recheck_hours_*`.

## הלוך וחזור / Round trip
`stay_nights` קובע כמה לילות בקפריסין, לדוגמה `[3, 4, 7]` מחפש חזרה אחרי 3, 4 או 7 לילות. `[]` = כיוון אחד בלבד.
החזרה היא מלרנקה לאותו שדה שממנו יצאתם (TLV או HFA), ו-4 המקומות נדרשים גם בטיסת החזור, באותה הצעה.
כל צירוף נוסף של לילות מכפיל את מספר החיפושים, אז בדקו עם `python -m flightwatch plan`.
