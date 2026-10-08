/* Читач сторінки відгуків Djinni (/my/inbox/) у ВЛАСНІЙ сесії користувача.
 *
 * Межа, через яку цей файл існує: сторінка за логіном, і автоматизувати вхід
 * означало б тримати чужі облікові дані й ризикувати акаунтом, який є єдиним
 * каналом пошуку. Тут сторінку відкриває людина, скрипт лише читає екран.
 *
 * Селектори встановлені за фактом 08.10.2026 розбором справжньої розмітки:
 *   рядок      .proposal.js-proposal   (data-id = ідентифікатор листування)
 *   компанія   a[href*="/jobs/company-"]
 *   позиція    .job_title a   (запасний варіант — a[href^="/my/inbox/"])
 *   рекрутер   .text-gray-600
 * Два попередні здогади про розмітку були хибні; тому тут нічого не
 * вгадується, а невідоме виводиться користувачеві, а не замовчується.
 */
(function () {
  "use strict";

  var API = "__API__", TOKEN = "__TOKEN__", SOURCE = "__SOURCE__";

  var WRONG = [
    [/\/my\/dashboard/, "це рекомендації за профілем, а не ваші відгуки"],
    [/\/my\/profile/, "це ваш профіль"],
    [/\/my\/stats/, "це статистика, окрема сторінка"],
    [/^\/jobs\/?$/, "це загальний список вакансій"]
  ];
  for (var w = 0; w < WRONG.length; w++) {
    if (WRONG[w][0].test(location.pathname)) {
      alert("jobtrack: не та сторінка.\n\n" + location.pathname + " — " + WRONG[w][1] +
            ".\n\nВідгуки лежать за адресою /my/inbox/ — відкрийте її й запустіть знову.");
      return;
    }
  }

  function text(el) { return el ? (el.textContent || "").replace(/\s+/g, " ").trim() : ""; }

  /* Слова → стани. Рядки взято з реального інтерфейсу Djinni, не вигадано.
     Порядок має значення: «не переглянуто» мусить перевірятись перед
     «переглянуто», а пряма відмова — перед загальною ознакою відповіді. */
  /* Автовідповідь НЕ є доказом перегляду.
   *
   * Знайдено 08.10 на першій же подачі: VCHASNO відповіли за три хвилини
   * текстом «Передали його на розгляд лідеру», під яким Djinni ставить
   * позначку «Це автоматична відповідь». Без цієї перевірки збирач зарахував
   * би її як «рекрутер відповів» і воронка показала б перегляд там, де його
   * не було.
   *
   * Це не окремий випадок, а механізм: з жовтня 2024 Djinni не дає
   * перепублікувати вакансію, не розібравши непрочитані відгуки, тож масова
   * автоматична відмова теж іде в статистику як відповідь. Єдине число,
   * заради якого ведеться журнал, від цього стало б неправдивим.
   */
  var AUTO = /це автоматична відповідь|автоматичн\w* відповід|automatic reply|auto-?reply|передали (його )?на розгляд|ваш відгук передано/i;

  function statusFrom(blob) {
    if (AUTO.test(blob))
      return { s: "auto_reply", why: "автовідповідь — не доказ перегляду" };
    if (/ваш відгук на цю позицію відхилено|відхилено|відмовл/i.test(blob))
      return { s: "rejected", why: "відмова" };
    if (/призупиня|призупинил|пауз|вакансію закрит|позицію закрит/i.test(blob))
      return { s: "rejected", why: "вакансію закрито" };
    if (/запрош|співбес|interview|созвон|дзвінок|calendly/i.test(blob))
      return { s: "invited", why: "запрошення" };
    if (/тестов|test task|тестове завдання/i.test(blob))
      return { s: "test_task", why: "тестове" };
    if (/офер|offer|пропозиці[юї] роботи/i.test(blob))
      return { s: "offer", why: "офер" };
    // «Ви відгукнулись» і більше нічого — відповіді не було взагалі.
    if (/ви відгукнулись/i.test(blob) && !/\bВи:/.test(blob))
      return { s: null, why: "лише подача, відповіді не було" };
    // Будь-який текст від рекрутера означає, що відгук прочитали.
    if (/дякую|вітаю|на жаль|доброго дня|добрий день|hello|hi\b/i.test(blob))
      return { s: "viewed", why: "рекрутер відповів" };
    return { s: null, why: null };
  }

  /* Дата: спершу <time datetime>, далі «8 жовтня» / «08.10.2026» у тексті.
     Якщо дати немає — НЕ підставляємо сьогодні: подача з вересня, записана
     сьогоднішнім числом, зіпсувала б розріз воронки за тижнями. */
  var MONTHS = ["січ", "лют", "берез", "квіт", "трав", "черв",
                "лип", "серп", "верес", "жовт", "листоп", "груд"];
  function dateFrom(box) {
    // Djinni показує відносний вік: «5mo», «8mo», «3d». Точного числа немає,
    // тож дата ПРИБЛИЗНА — і це позначається в нотатці, а не замовчується.
    var rel = text(box).match(/\b(\d+)\s*(mo|d|h|w|y)\b/);
    if (rel) {
      var n = parseInt(rel[1], 10), d = new Date();
      if (rel[2] === "mo") d.setMonth(d.getMonth() - n);
      else if (rel[2] === "d") d.setDate(d.getDate() - n);
      else if (rel[2] === "w") d.setDate(d.getDate() - n * 7);
      else if (rel[2] === "y") d.setFullYear(d.getFullYear() - n);
      else if (rel[2] === "h") { /* сьогодні */ }
      return d.toISOString().slice(0, 10);
    }
    var t = box.querySelector("time[datetime]");
    if (t) { var d = t.getAttribute("datetime").slice(0, 10); if (/^\d{4}-\d\d-\d\d$/.test(d)) return d; }
    var blob = text(box);
    var m = blob.match(/(\d{1,2})\.(\d{1,2})\.(\d{4})/);
    if (m) return m[3] + "-" + ("0" + m[2]).slice(-2) + "-" + ("0" + m[1]).slice(-2);
    m = blob.match(/(\d{1,2})\s+([а-яіїє]{3,})/i);
    if (m) {
      for (var i = 0; i < MONTHS.length; i++) {
        if (m[2].toLowerCase().indexOf(MONTHS[i]) === 0) {
          var now = new Date(), year = now.getFullYear();
          if (i > now.getMonth()) year -= 1;   // майбутній місяць = торік
          return year + "-" + ("0" + (i + 1)).slice(-2) + "-" + ("0" + m[1]).slice(-2);
        }
      }
    }
    return null;
  }

  function collect() { return collectIn(document); }

  function collectIn(root) {
    var rows = [], tails = [];
    var boxes = root.querySelectorAll(".proposal, .js-proposal");
    for (var i = 0; i < boxes.length; i++) {
      var box = boxes[i];
      var id = box.getAttribute("data-id") || "";
      // Посилання на компанію містить і назву, і крапку-роздільник, і ім'я
      // рекрутера. Перший прогін 08.10 записав «Insiders · Khrystyna» як назву
      // компанії — беремо лише перший внутрішній <span>, а як запобіжник
      // відтинаємо все після роздільника.
      var companyLink = box.querySelector('a[href*="/jobs/company-"]');
      var companyEl = companyLink ? (companyLink.querySelector("span") || companyLink) : null;
      var posEl = box.querySelector('.job_title a, a[href^="/my/inbox/"]:not(.proposal-absolute-link)');
      var blob = text(box);
      var st = statusFrom(blob);

      rows.push({
        url: id ? "https://djinni.co/my/inbox/" + id + "/" : null,
        company: (text(companyEl).split("·")[0].trim()) || "—",
        position: text(posEl) || "—",
        applied_on: dateFrom(box),
        status: st.s,
        status_on: st.s ? dateFrom(box) : null,
        // Дата, виведена з «5mo», точна лише до місяця. Позначаємо прямо в
        // записі: невідома точність гірша за відому неточність.
        note: AUTO.test(blob)
              ? "автовідповідь — перегляд НЕ підтверджено"
              : (/\b\d+\s*(mo|w|y)\b/.test(blob)
                 ? "дата приблизна — обчислена з відносного віку на сторінці"
                 : (st.why || null))
      });

      // Решта тексту рядка — щоб побачити, якими словами Djinni позначає стан.
      // Статус у видимій частині розмітки відсутній, тож перший прогін
      // заразом є словником.
      tails.push((st.why ? "[" + st.why + "] " : "[?] ") + blob.slice(0, 200));
    }
    return { rows: rows, tails: tails };
  }

  function send(rows, dry) {
    return fetch(API + "/api/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Sync-Token": TOKEN },
      body: JSON.stringify({ source: SOURCE, items: rows, dry_run: dry })
    }).then(function (r) { return r.json(); });
  }

  /* Архів — окрема сторінка (?bucket=archive), і вантажиться власним запитом.
     Саме там 08.10 знайшлись десять відгуків, яких не було у вхідних: без
     обходу кошиків журнал бачив би четвертину реальної картини. */
  function fromHtml(html) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    var saved = document.body;
    try { return collectIn(doc); } finally { saved; }
  }

  function withBucket(bucket) {
    return fetch("/my/inbox?bucket=" + bucket, { credentials: "include" })
      .then(function (r) { return r.text(); })
      .then(function (html) { return fromHtml(html); })
      .catch(function () { return { rows: [], tails: [] }; });
  }

  var found = collect();
  Promise.all([withBucket("archive")]).then(function (extra) {
    var seen = {};
    for (var i = 0; i < found.rows.length; i++) seen[found.rows[i].url] = true;
    for (var e = 0; e < extra.length; e++) {
      for (var j = 0; j < extra[e].rows.length; j++) {
        var row = extra[e].rows[j];
        if (row.url && seen[row.url]) continue;
        seen[row.url] = true;
        found.rows.push(row);
        found.tails.push(extra[e].tails[j]);
      }
    }
    run(found);
  });

  function run(found) {
  if (!found.rows.length) {
    alert("jobtrack: на цій сторінці немає рядків .proposal.\n\n" +
          "Якщо відгуки видно очима — надішліть автору розмітку одного рядка.");
    return;
  }

  console.log("jobtrack — текст рядків (для уточнення словника статусів):\n" +
              found.tails.join("\n\n"));

  send(found.rows, true).then(function (report) {
    var msg = "jobtrack — попередній перегляд (нічого ще не записано)\n\n" +
      "Знайдено листувань: " + report.received + "\n" +
      "Буде створено нових: " + report.created + "\n" +
      "Зіставлено з наявними: " + report.matched + "\n" +
      "Буде додано подій: " + report.events_added + "\n\n";
    for (var i = 0; i < found.rows.length; i++) {
      var r = found.rows[i];
      msg += "• " + r.company + " — " + r.position +
             "  [" + (r.status || "стан не розпізнано") + "]" +
             (r.applied_on ? " від " + r.applied_on : " (дата не знайдена)") + "\n";
    }
    if (report.ambiguous.length) msg += "\nНеоднозначні: " + report.ambiguous.join(", ") + "\n";
    msg += "\nПовний текст рядків — у консолі.\n\nЗаписати?";

    if (!confirm(msg)) return;
    send(found.rows, false).then(function (done) {
      alert("Записано: " + done.created + " нових, " + done.events_added + " подій.\n\n" +
            "Якщо стан не розпізнався — скопіюйте вивід із консолі в розмову,\n" +
            "і словник статусів буде доповнено.");
    });
  }).catch(function (e) {
    alert("jobtrack: не вдалося звернутися до " + API + "\n" + e);
  });
  }
})();
