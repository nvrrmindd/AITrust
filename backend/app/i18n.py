"""User-facing messages in Russian, English and Kazakh.

The language of the current check lives in a ContextVar: it is set once when a check starts and every
asyncio task created inside the check inherits it, so deep code just calls tr("key", ...).
Kazakh strings were written by the team and should be proofread by a native speaker before release.
"""
from __future__ import annotations

from contextvars import ContextVar

LANGS = ("ru", "en", "kk")
LANG: ContextVar[str] = ContextVar("lang", default="ru")

# how to ask the LLM to write its "reason" field
LLM_LANGUAGE = {"ru": "по-русски", "en": "in English (на английском языке)", "kk": "на казахском языке (қазақ тілінде)"}


def norm_lang(value: str | None) -> str:
    v = (value or "").lower()[:2]
    return v if v in LANGS else "ru"


def current() -> str:
    return LANG.get()


def tr(key: str, **kw) -> str:
    entry = MESSAGES[key]
    text = entry.get(LANG.get()) or entry["ru"]
    return text.format(**kw) if kw else text


MESSAGES: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------ sources
    "src.domain_missing": {
        "ru": "Домен «{host}» не существует — такого сайта нет.",
        "en": "The domain “{host}” does not exist — there is no such website.",
        "kk": "«{host}» домені жоқ — мұндай сайт жоқ.",
    },
    "src.internal": {
        "ru": "Ссылка ведёт на внутренний адрес — из соображений безопасности не открываем.",
        "en": "The link points to an internal address — we do not open it for security reasons.",
        "kk": "Сілтеме ішкі мекенжайға апарады — қауіпсіздік үшін оны ашпаймыз.",
    },
    "src.no_response": {
        "ru": "Сайт не ответил ({err}). Это не значит, что источника нет.",
        "en": "The website did not respond ({err}). This does not mean the source does not exist.",
        "kk": "Сайт жауап бермеді ({err}). Бұл дереккөздің жоқ екенін білдірмейді.",
    },
    "src.page_404": {
        "ru": "Страница не существует (HTTP {status}). ИИ дал ссылку, которая никуда не ведёт.",
        "en": "The page does not exist (HTTP {status}). The AI gave a link that leads nowhere.",
        "kk": "Бет жоқ (HTTP {status}). ЖИ ешқайда апармайтын сілтеме берген.",
    },
    "src.blocked": {
        "ru": "Сайт не пустил нас (HTTP {status}): пейвол или защита от ботов. Это не значит, что источника нет.",
        "en": "The website blocked us (HTTP {status}): a paywall or bot protection. This does not mean the source does not exist.",
        "kk": "Сайт бізді кіргізбеді (HTTP {status}): ақылы қолжетімділік немесе боттардан қорғаныс. Бұл дереккөздің жоқ екенін білдірмейді.",
    },
    "src.soft_404": {
        "ru": "Сайт открылся, но это заглушка «{title}» — нужной страницы нет.",
        "en": "The website opened, but it is a placeholder page “{title}” — the page itself is missing.",
        "kk": "Сайт ашылды, бірақ бұл «{title}» бос беті — қажетті бет жоқ.",
    },
    "src.nothing": {
        "ru": "У источника нет ни ссылки, ни DOI, ни названия — проверить нечего.",
        "en": "The source has no link, no DOI and no title — there is nothing to check.",
        "kk": "Дереккөзде сілтеме де, DOI да, атау да жоқ — тексеретін ештеңе жоқ.",
    },
    "src.failed": {
        "ru": "Не удалось проверить источник: {err}.",
        "en": "Could not check the source: {err}.",
        "kk": "Дереккөзді тексеру мүмкін болмады: {err}.",
    },
    "src.doi_missing": {
        "ru": "DOI {doi} не зарегистрирован в мировом реестре DOI. Такой публикации не существует.",
        "en": "DOI {doi} is not registered in the global DOI registry. This publication does not exist.",
        "kk": "DOI {doi} әлемдік DOI тізілімінде тіркелмеген. Мұндай басылым жоқ.",
    },
    "src.doi_no_meta": {
        "ru": "DOI {doi} зарегистрирован, но метаданные недоступны.",
        "en": "DOI {doi} is registered, but its metadata is unavailable.",
        "kk": "DOI {doi} тіркелген, бірақ оның метадеректері қолжетімсіз.",
    },
    "src.doi_down": {
        "ru": "Реестры DOI не ответили — попробуйте позже.",
        "en": "The DOI registries did not respond — try again later.",
        "kk": "DOI тізілімдері жауап бермеді — кейінірек қайталап көріңіз.",
    },
    "src.doi_other_work": {
        "ru": "DOI существует, но ведёт на другую работу: «{title}». ИИ склеил ссылку из чужих данных.",
        "en": "The DOI exists but leads to a different work: “{title}”. The AI stitched the reference together from someone else's data.",
        "kk": "DOI бар, бірақ басқа жұмысқа апарады: «{title}». ЖИ сілтемені бөтен деректерден құрастырған.",
    },
    "src.pub_mismatch": {
        "ru": "Публикация существует, но данные в ответе не совпадают с реальными.",
        "en": "The publication exists, but the details in the text do not match the real ones.",
        "kk": "Басылым бар, бірақ мәтіндегі деректер нақты деректермен сәйкес келмейді.",
    },
    "src.pub_ok": {
        "ru": "Публикация существует, данные совпадают.",
        "en": "The publication exists and the details match.",
        "kk": "Басылым бар, деректері сәйкес келеді.",
    },
    "src.page_no_text": {
        "ru": "Страница существует, но текст не удалось извлечь (вероятно, страница рисуется скриптами).",
        "en": "The page exists, but its text could not be extracted (it is probably rendered by scripts).",
        "kk": "Бет бар, бірақ мәтінін алу мүмкін болмады (бет скрипттермен жасалатын болуы мүмкін).",
    },
    "src.page_ok": {
        "ru": "Страница существует и прочитана.",
        "en": "The page exists and was read.",
        "kk": "Бет бар және оқылды.",
    },
    "src.work_mismatch": {
        "ru": "Работа с таким названием есть, но данные в ответе не совпадают.",
        "en": "A work with this title exists, but the details in the text do not match.",
        "kk": "Осындай атаулы жұмыс бар, бірақ мәтіндегі деректер сәйкес келмейді.",
    },
    "src.work_ok": {
        "ru": "Работа найдена в научных базах, данные совпадают.",
        "en": "The work was found in scholarly databases and the details match.",
        "kk": "Жұмыс ғылыми базалардан табылды, деректері сәйкес келеді.",
    },
    "src.openalex_busy": {
        "ru": "В Crossref такой работы нет, но вторая база (OpenAlex) сейчас перегружена. Чтобы не назвать настоящий источник выдуманным, вердикт не выносим — повторите проверку через минуту.",
        "en": "Crossref has no such work, but the second database (OpenAlex) is overloaded right now. To avoid calling a real source fake, we give no verdict — retry in a minute.",
        "kk": "Crossref-те мұндай жұмыс жоқ, бірақ екінші база (OpenAlex) қазір шамадан тыс жүктелген. Нақты дереккөзді жалған деп атамау үшін қорытынды шығармаймыз — бір минуттан кейін қайта тексеріңіз.",
    },
    "src.crossref_busy": {
        "ru": "В OpenAlex такой работы нет, но Crossref сейчас не ответил. Чтобы не назвать настоящий источник выдуманным, вердикт не выносим — повторите проверку через минуту.",
        "en": "OpenAlex has no such work, but Crossref did not respond right now. To avoid calling a real source fake, we give no verdict — retry in a minute.",
        "kk": "OpenAlex-те мұндай жұмыс жоқ, бірақ Crossref қазір жауап бермеді. Нақты дереккөзді жалған деп атамау үшін қорытынды шығармаймыз — бір минуттан кейін қайта тексеріңіз.",
    },
    "src.dbs_busy": {
        "ru": "Научные базы Crossref и OpenAlex сейчас не ответили — повторите проверку через минуту.",
        "en": "The Crossref and OpenAlex databases did not respond right now — retry in a minute.",
        "kk": "Crossref және OpenAlex ғылыми базалары қазір жауап бермеді — бір минуттан кейін қайта тексеріңіз.",
    },
    "src.fake_work": {
        "ru": "Такой научной работы нет ни в Crossref, ни в OpenAlex (сотни миллионов публикаций). Скорее всего, ИИ её выдумал.",
        "en": "No such scholarly work exists in Crossref or OpenAlex (hundreds of millions of publications). Most likely the AI made it up.",
        "kk": "Мұндай ғылыми жұмыс Crossref-те де, OpenAlex-те де жоқ (жүздеген миллион басылым). Бәлкім, оны ЖИ ойдан шығарған.",
    },
    "src.nearest": {
        "ru": " Ближайшее похожее: «{title}».",
        "en": " The closest match: “{title}”.",
        "kk": " Ең жақын ұқсасы: «{title}».",
    },
    "src.unchecked_nodb": {
        "ru": "У источника нет ссылки и DOI, а в научных базах он не найден. Проверьте его вручную — сам факт, что источник нельзя открыть, уже повод не доверять.",
        "en": "The source has no link or DOI and was not found in scholarly databases. Check it by hand — a source that cannot be opened is already a reason for doubt.",
        "kk": "Дереккөзде сілтеме мен DOI жоқ, ғылыми базалардан да табылмады. Оны қолмен тексеріңіз — ашуға болмайтын дереккөздің өзі күмән тудырады.",
    },
    "diff.year": {
        "ru": "год: в тексте {a}, на самом деле {b}",
        "en": "year: {a} in the text, actually {b}",
        "kk": "жылы: мәтінде {a}, шын мәнінде {b}",
    },
    "diff.authors": {
        "ru": "авторы: в тексте {a}; на самом деле {b}",
        "en": "authors: {a} in the text; actually {b}",
        "kk": "авторлары: мәтінде {a}; шын мәнінде {b}",
    },
    "diff.title": {
        "ru": "название: на самом деле «{b}»",
        "en": "title: actually “{b}”",
        "kk": "атауы: шын мәнінде «{b}»",
    },
    # ------------------------------------------------------------------ judge
    "j.quote_dropped": {
        "ru": "Модель-судья не смогла привести дословную цитату из источника — её вердикт отброшен.",
        "en": "The judge model could not give a verbatim quote from the source — its verdict was discarded.",
        "kk": "Төреші модель дереккөзден сөзбе-сөз дәйексөз келтіре алмады — оның қорытындысы алынып тасталды.",
    },
    "j.unrecognized": {"ru": "Источник не распознан.", "en": "The source was not recognised.", "kk": "Дереккөз танылмады."},
    "j.source_missing": {
        "ru": "Утверждение опирается на источник, которого не существует. {detail}",
        "en": "The claim relies on a source that does not exist. {detail}",
        "kk": "Тұжырым жоқ дереккөзге сүйенеді. {detail}",
    },
    "j.no_text": {"ru": "Текст источника недоступен.", "en": "The source text is unavailable.", "kk": "Дереккөз мәтіні қолжетімсіз."},
    "j.cannot_read": {
        "ru": "Не удалось прочитать источник, поэтому честно не выносим вердикт. {why}",
        "en": "We could not read the source, so we honestly give no verdict. {why}",
        "kk": "Дереккөзді оқу мүмкін болмады, сондықтан адал түрде қорытынды шығармаймыз. {why}",
    },
    "j.llm_fail": {
        "ru": "Сбой модели-судьи: {err}",
        "en": "The judge model failed: {err}",
        "kk": "Төреші модельде ақау: {err}",
    },
    "j.no_quote": {
        "ru": "Модель нашла что-то похожее, но не смогла подтвердить это дословной цитатой. Вердикт не выносим.",
        "en": "The model found something similar but could not back it with a verbatim quote. No verdict.",
        "kk": "Модель ұқсас нәрсе тапты, бірақ оны сөзбе-сөз дәйексөзбен растай алмады. Қорытынды шығармаймыз.",
    },
    "j.numbers_note": {
        "ru": "Цифры в утверждении не совпадают с цифрами в источнике.",
        "en": "The numbers in the claim do not match the numbers in the source.",
        "kk": "Тұжырымдағы сандар дереккөздегі сандармен сәйкес келмейді.",
    },
    "j.numbers_reason": {
        "ru": "Источник говорит о том же, но с другими числами: в тексте — {a}, в источнике — {b}.",
        "en": "The source talks about the same thing but with different numbers: {a} in the text, {b} in the source.",
        "kk": "Дереккөз сол туралы айтады, бірақ басқа сандармен: мәтінде — {a}, дереккөзде — {b}.",
    },
    "j.narrower": {
        "ru": "Источник говорит о более узком или осторожном утверждении, чем текст.",
        "en": "The source makes a narrower or more cautious statement than the text.",
        "kk": "Дереккөз мәтінге қарағанда тар немесе сақ тұжырым жасайды.",
    },
    "j.abstract_missing": {
        "ru": "В аннотации статьи этого нет, а полный текст недоступен — подтвердить или опровергнуть нельзя.",
        "en": "The abstract does not mention this and the full text is unavailable — it can be neither confirmed nor refuted.",
        "kk": "Мақала аннотациясында бұл жоқ, ал толық мәтіні қолжетімсіз — растау да, теріске шығару да мүмкін емес.",
    },
    "j.not_in_source": {
        "ru": "Источник существует и прочитан, но этого утверждения в нём нет.",
        "en": "The source exists and was read, but this claim is not in it.",
        "kk": "Дереккөз бар және оқылды, бірақ онда бұл тұжырым жоқ.",
    },
    "j.distorted_note": {
        "ru": "Данные источника в тексте искажены: {x}",
        "en": "The source details in the text are distorted: {x}",
        "kk": "Мәтіндегі дереккөз деректері бұрмаланған: {x}",
    },
    "j.abstract_note": {
        "ru": "Проверено по аннотации статьи (полный текст недоступен).",
        "en": "Checked against the article abstract (the full text is unavailable).",
        "kk": "Мақала аннотациясы бойынша тексерілді (толық мәтіні қолжетімсіз).",
    },
    "j.attack_nothing": {
        "ru": "Источник не указан, а поиск ({prov}) не нашёл ни одной страницы по теме. Подтверждений нет — используйте это утверждение с осторожностью.",
        "en": "No source was given, and the search ({prov}) found no page on the topic. There is no confirmation — use this claim with caution.",
        "kk": "Дереккөз көрсетілмеген, ал іздеу ({prov}) тақырып бойынша бірде-бір бет таппады. Растау жоқ — бұл тұжырымды сақтықпен қолданыңыз.",
    },
    "j.dropped": {
        "ru": "{n} цитат(ы) модели не нашлись в источниках дословно и были отброшены.",
        "en": "{n} of the model's quotes were not found verbatim in the sources and were discarded.",
        "kk": "Модельдің {n} дәйексөзі дереккөздерден сөзбе-сөз табылмады және алынып тасталды.",
    },
    "j.weak_refute": {
        "ru": "Опровержение найдено в одном источнике невысокой надёжности — стоит перепроверить.",
        "en": "The refutation comes from a single low-reliability source — worth double-checking.",
        "kk": "Теріске шығару сенімділігі төмен бір ғана дереккөзден табылды — қайта тексерген жөн.",
    },
    "j.other_numbers": {
        "ru": "Найденные источники приводят другие числа.",
        "en": "The sources found give different numbers.",
        "kk": "Табылған дереккөздер басқа сандарды келтіреді.",
    },
    "j.weak_support": {
        "ru": "Нашли подтверждение только на одном сайте невысокой надёжности. Этого мало, чтобы считать факт доказанным. ",
        "en": "Confirmation was found on only one low-reliability website. That is not enough to consider the fact proven. ",
        "kk": "Растау сенімділігі төмен бір ғана сайттан табылды. Фактіні дәлелденген деп санауға бұл жеткіліксіз. ",
    },
    "j.no_verified": {
        "ru": "Модель что-то нашла, но не подтвердила это дословными цитатами. ",
        "en": "The model found something but did not back it with verbatim quotes. ",
        "kk": "Модель бірдеңе тапты, бірақ оны сөзбе-сөз дәйексөздермен растамады. ",
    },
    "j.neither": {
        "ru": "На найденных страницах нет ни подтверждения, ни опровержения.",
        "en": "The pages found neither confirm nor refute this.",
        "kk": "Табылған беттерде растау да, теріске шығару да жоқ.",
    },
    "j.attack_note": {
        "ru": "Источник не указан — искали и подтверждения, и опровержения ({prov}, прочитано страниц: {n}).",
        "en": "No source was given — we searched for both confirmation and refutation ({prov}, pages read: {n}).",
        "kk": "Дереккөз көрсетілмеген — растауды да, теріске шығаруды да іздедік ({prov}, оқылған беттер: {n}).",
    },
    "j.llm_quota": {
        "ru": "Бесплатный лимит языковой модели сейчас исчерпан, поэтому вердикт не вынесен. Попробуйте позже: лимиты обновляются в течение суток.",
        "en": "The free language-model limit is exhausted right now, so no verdict was given. Try again later: the limits refresh within a day.",
        "kk": "Тілдік модельдің тегін лимиті қазір таусылды, сондықтан қорытынды шығарылмады. Кейінірек қайталап көріңіз: лимиттер бір тәулік ішінде жаңарады.",
    },
    "j.fallback_note": {
        "ru": "Источник по ссылке прочитать не удалось, поэтому утверждение проверено по открытым источникам в интернете.",
        "en": "The cited source could not be read, so the claim was checked against open sources on the web.",
        "kk": "Сілтемедегі дереккөзді оқу мүмкін болмады, сондықтан тұжырым интернеттегі ашық дереккөздер бойынша тексерілді.",
    },
    "err.llm_busy": {
        "ru": "Не удалось разобрать текст: бесплатные лимиты языковой модели сейчас исчерпаны. Попробуйте позже или откройте готовые примеры — они работают без лимитов.",
        "en": "Could not parse the text: the free language-model limits are exhausted right now. Try again later or open the ready-made examples — they work without limits.",
        "kk": "Мәтінді талдау мүмкін болмады: тілдік модельдің тегін лимиттері қазір таусылды. Кейінірек қайталап көріңіз немесе дайын мысалдарды ашыңыз — олар лимитсіз жұмыс істейді.",
    },
    "prov.web": {"ru": "веб-поиск", "en": "web search", "kk": "веб-іздеу"},
    "prov.wiki": {"ru": "только Википедия", "en": "Wikipedia only", "kk": "тек Уикипедия"},
    "certainty.exact": {"ru": "точное число {n}", "en": "exact number {n}", "kk": "нақты сан {n}"},
    # ------------------------------------------------------------------ pipeline / documents / API
    "stage.extract": {
        "ru": "Разбираю текст на утверждения и источники…",
        "en": "Splitting the text into claims and sources…",
        "kk": "Мәтінді тұжырымдар мен дереккөздерге бөліп жатырмын…",
    },
    "stage.verify": {
        "ru": "Проверяю источники и ищу опровержения…",
        "en": "Checking sources and looking for refutations…",
        "kk": "Дереккөздерді тексеріп, теріске шығаруларды іздеп жатырмын…",
    },
    "stage.bib": {"ru": "Разбираю список литературы…", "en": "Reading the reference list…", "kk": "Әдебиеттер тізімін талдап жатырмын…"},
    "stage.bib_verify": {
        "ru": "Проверяю источников: {a}, утверждений: {b}…",
        "en": "Checking {a} sources and {b} claims…",
        "kk": "Тексеріліп жатыр: {a} дереккөз, {b} тұжырым…",
    },
    "bib.no_refs": {
        "ru": "Заголовок списка литературы есть, но ссылок под ним не нашлось.",
        "en": "There is a reference-list heading, but no references under it.",
        "kk": "Әдебиеттер тізімінің тақырыбы бар, бірақ оның астында сілтемелер табылмады.",
    },
    "bib.selected": {
        "ru": "В документе нет списка литературы, поэтому проверяем утверждения о фактах и числах из всего текста. Титульный лист, личные данные, даты и обязанности не проверяем: их нельзя сверить с открытыми источниками.",
        "en": "The document has no reference list, so we check factual and numeric claims from the whole text. The title page, personal data, dates and duties are not checked: they cannot be compared with open sources.",
        "kk": "Құжатта әдебиеттер тізімі жоқ, сондықтан бүкіл мәтіннен фактілер мен сандар туралы тұжырымдарды тексереміз. Титулдық бет, жеке деректер, күндер мен міндеттер тексерілмейді: оларды ашық дереккөздермен салыстыру мүмкін емес.",
    },
    "bib.nothing": {
        "ru": "В документе не нашлось утверждений, которые можно сверить с открытыми источниками: только личные данные, даты, обязанности и описание работы. Такие сведения Trustable? не проверяет.",
        "en": "The document has no claims that can be compared with open sources: only personal data, dates, duties and a description of the work. Trustable? does not check such information.",
        "kk": "Құжатта ашық дереккөздермен салыстыруға болатын тұжырымдар табылмады: тек жеке деректер, күндер, міндеттер және жұмыс сипаттамасы. Trustable? мұндай мәліметтерді тексермейді.",
    },
    "internal_error": {
        "ru": "Внутренняя ошибка проверки: {err}.",
        "en": "Internal checking error: {err}.",
        "kk": "Тексерудің ішкі қатесі: {err}.",
    },
    "api.too_long": {
        "ru": "Слишком длинный текст: максимум {n} символов.",
        "en": "The text is too long: {n} characters at most.",
        "kk": "Мәтін тым ұзын: ең көбі {n} таңба.",
    },
    "api.no_key": {
        "ru": "Сервер не настроен: не задан ключ языковой модели. Попробуйте один из примеров.",
        "en": "The server is not configured: no language-model key is set. Try one of the examples.",
        "kk": "Сервер бапталмаған: тілдік модель кілті жоқ. Мысалдардың бірін қолданып көріңіз.",
    },
    "api.rate": {
        "ru": "Слишком много проверок подряд. Подождите немного.",
        "en": "Too many checks in a row. Please wait a little.",
        "kk": "Қатарынан тым көп тексеру. Біраз күте тұрыңыз.",
    },
    "api.sample_missing": {"ru": "Пример не найден", "en": "Example not found", "kk": "Мысал табылмады"},
    "api.report_missing": {"ru": "Отчёт не найден", "en": "Report not found", "kk": "Есеп табылмады"},
    "doc.format": {
        "ru": "Неподдерживаемый формат. Загрузите .docx, .pdf, .txt или .md.",
        "en": "Unsupported format. Upload a .docx, .pdf, .txt or .md file.",
        "kk": "Қолдау көрсетілмейтін формат. .docx, .pdf, .txt немесе .md файлын жүктеңіз.",
    },
    "doc.too_big": {"ru": "Файл больше 10 МБ.", "en": "The file is larger than 10 MB.", "kk": "Файл 10 МБ-тан үлкен."},
    "doc.empty": {"ru": "Файл пустой.", "en": "The file is empty.", "kk": "Файл бос."},
    "doc.no_text": {"ru": "В файле нет текста.", "en": "The file has no text.", "kk": "Файлда мәтін жоқ."},
    "doc.docx_bad": {
        "ru": "Не удалось открыть .docx — файл повреждён или это не Word-документ.",
        "en": "Could not open the .docx — the file is damaged or it is not a Word document.",
        "kk": ".docx файлын ашу мүмкін болмады — файл бүлінген немесе бұл Word құжаты емес.",
    },
    "doc.pdf_bad": {
        "ru": "Не удалось открыть PDF — файл повреждён или защищён паролем.",
        "en": "Could not open the PDF — the file is damaged or password-protected.",
        "kk": "PDF файлын ашу мүмкін болмады — файл бүлінген немесе құпиясөзбен қорғалған.",
    },
    "doc.pdf_scan": {
        "ru": "PDF — это картинка, текст не найден. Загрузите .docx или PDF с текстовым слоем.",
        "en": "This PDF is an image, no text was found. Upload a .docx or a PDF with a text layer.",
        "kk": "Бұл PDF — сурет, мәтін табылмады. .docx немесе мәтін қабаты бар PDF жүктеңіз.",
    },
}


# ---------------------------------------------------------------------------- summary headline

def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n) % 100
    if 10 < n < 20:
        return many
    n %= 10
    return one if n == 1 else few if 2 <= n <= 4 else many


def headline(total_sources: int, missing: int, mism: int, bad: int, ok: int, n_results: int, weak: int) -> str:
    lang = LANG.get()
    parts: list[str] = []
    if lang == "en":
        if total_sources and missing:
            parts.append(f"{missing} of {total_sources} sources do not exist")
        if mism:
            parts.append(f"{mism} source{'s are' if mism != 1 else ' is'} distorted")
        if bad:
            parts.append(f"{bad} claim{'s contradict' if bad != 1 else ' contradicts'} the sources")
        if not parts:
            h = f"Confirmed {ok} of {n_results} claims" if n_results else "No checkable claims found"
            return h + (f", {weak} without evidence." if weak else ".")
        text = "; ".join(parts)
    elif lang == "kk":
        if total_sources and missing:
            parts.append(f"жоқ дереккөздер: {missing} / {total_sources}")
        if mism:
            parts.append(f"бұрмаланған дереккөздер: {mism}")
        if bad:
            parts.append(f"дереккөздерге қайшы тұжырымдар: {bad}")
        if not parts:
            h = f"Расталған тұжырымдар: {ok} / {n_results}" if n_results else "Тексерілетін тұжырымдар табылмады"
            return h + (f", дәлелсіз: {weak}." if weak else ".")
        text = "; ".join(parts)
    else:
        if total_sources and missing:
            parts.append(f"{missing} из {total_sources} {_ru_plural(total_sources, 'источника', 'источников', 'источников')} не существуют")
        if mism:
            parts.append(f"{mism} {_ru_plural(mism, 'источник искажён', 'источника искажены', 'источников искажены')}")
        if bad:
            parts.append(f"{bad} {_ru_plural(bad, 'утверждение противоречит', 'утверждения противоречат', 'утверждений противоречат')} источникам")
        if not parts:
            h = f"Подтверждено {ok} из {n_results} утверждений" if n_results else "Проверяемых утверждений не найдено"
            return h + (f", {weak} — без доказательств." if weak else ".")
        text = "; ".join(parts)
    return text[0].upper() + text[1:] + "."
