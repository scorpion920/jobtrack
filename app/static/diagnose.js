/* Діагностика розмітки сторінки відгуків.
 *
 * Нічого не шле і нічого не записує. Друкує в консоль структуру сторінки,
 * щоб селектори писалися за фактом, а не за здогадом: автор коду цієї
 * сторінки не бачить, вона за логіном.
 *
 * Результат копіюється у буфер обміну одним рядком — лишається вставити.
 */
(function () {
  "use strict";
  var out = [];
  function say(s) { out.push(s); }

  say("URL: " + location.href);
  say("TITLE: " + document.title);
  say("");

  // Які взагалі посилання є на сторінці і скільки
  var groups = {};
  var links = document.querySelectorAll("a[href]");
  for (var i = 0; i < links.length; i++) {
    var h = links[i].getAttribute("href") || "";
    var key = h.split("?")[0].replace(/\d+/g, "N").replace(/-[a-z0-9-]{6,}/gi, "-SLUG");
    groups[key] = (groups[key] || 0) + 1;
  }
  var pairs = Object.keys(groups).map(function (k) { return [k, groups[k]]; });
  pairs.sort(function (a, b) { return b[1] - a[1]; });
  say("ФОРМИ ПОСИЛАНЬ (топ 18, формат «шаблон × скільки»):");
  for (var j = 0; j < Math.min(18, pairs.length); j++) {
    say("  " + pairs[j][1] + "× " + pairs[j][0]);
  }
  say("");

  // Рядки списку шукаємо не за найчастішим класом — так ми один раз уже
  // витягли навігацію замість даних, — а за ПОСИЛАННЯМИ, схожими на записи:
  // однаковий шаблон адреси з числовим ідентифікатором, що трапляється 2+ рази.
  var itemLinks = [];
  for (var p = 0; p < pairs.length; p++) {
    var pat = pairs[p][0];
    if (pairs[p][1] < 2) continue;
    if (!/N/.test(pat)) continue;                 // без числового id — навряд запис
    if (/^(#|https?:)/.test(pat)) continue;       // якорі й зовнішні — не записи
    itemLinks.push(pat);
  }
  say("СХОЖЕ НА ЗАПИСИ СПИСКУ (шаблони з числовим id): " +
      (itemLinks.length ? itemLinks.join(", ") : "не знайдено"));
  say("");

  // Беремо реальні посилання за першим таким шаблоном і піднімаємось до рядка.
  var rowHtml = [];
  if (itemLinks.length) {
    var rx = new RegExp(itemLinks[0].replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
                                     .replace("N", "\\d+")
                                     .replace("-SLUG", "[-a-z0-9]*"));
    for (var q = 0; q < links.length && rowHtml.length < 2; q++) {
      var href = links[q].getAttribute("href") || "";
      if (!rx.test(href)) continue;
      // Піднімаємось, доки контейнер не стане помітно більшим за саме посилання:
      // рядок списку містить і назву, і компанію, і статус.
      var node = links[q], up = 0;
      while (node.parentElement && up < 4 &&
             node.outerHTML.length < links[q].outerHTML.length + 150) {
        node = node.parentElement; up++;
      }
      rowHtml.push(node.outerHTML.replace(/\s+/g, " "));
    }
  }

  say("РОЗМІТКА ДВОХ ПЕРШИХ РЯДКІВ СПИСКУ:");
  if (!rowHtml.length) {
    say("  не знайдено — надішліть автору скріншот сторінки або HTML одного рядка");
  }
  for (var r = 0; r < rowHtml.length; r++) {
    say("--- рядок #" + (r + 1) + " (" + rowHtml[r].length + " символів, показано 1400) ---");
    say(rowHtml[r].slice(0, 1400));
  }
  say("");

  var text = out.join("\n");
  console.log(text);
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(function () {
      alert("jobtrack: діагностику скопійовано в буфер обміну (" + text.length +
            " символів).\nВставте її в розмову — селектори буде написано за фактом.");
    }, function () { alert("jobtrack: дивіться вивід у консолі (скопіювати не вдалось)."); });
  } else {
    alert("jobtrack: дивіться вивід у консолі.");
  }
})();
