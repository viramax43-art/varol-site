const countries = require("i18n-iso-countries");
const cc = require("currency-codes");

countries.registerLocale(require("i18n-iso-countries/langs/ru.json"));
countries.registerLocale(require("i18n-iso-countries/langs/en.json"));

const list = countries.getNames("ru", {select: "official"});
const listEng = countries.getNames("en", {select: "official"});

function getFlagEmoji(countryCode) {
  const codePoints = countryCode
    .toUpperCase()
    .split('')
    .map(char =>  127397 + char.charCodeAt());
  return String.fromCodePoint(...codePoints);
}

const supported = ["EUR", "USD", "PLN", "KZT", "AZN", "UAH", "RUB"];

let result = "const countryDictionary = [\n";
for (const [code, nameRus] of Object.entries(list)) {
  const nameEng = listEng[code] || "";
  const flag = getFlagEmoji(code);
  const currencyInfo = cc.country(nameEng) || [];
  let currency = "USD";
  if (currencyInfo.length > 0) {
      currency = currencyInfo[0].code;
  }
  
  if (["AT", "BE", "CY", "EE", "FI", "FR", "DE", "GR", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PT", "SK", "SI", "ES"].includes(code)) {
      currency = "EUR";
  }
  if (code === "US") currency = "USD";
  if (code === "RU") currency = "RUB";
  if (code === "GB") currency = "EUR"; // Since GBP is not in the list, default to EUR for GB or USD? Let's let the supported fallback handle it to USD. Wait, in old list, GB was EUR.
  if (code === "KZ") currency = "KZT";
  if (code === "BY") currency = "RUB"; // Default BY to RUB since BYN not supported

  if (code === "GB") currency = "EUR"; 
  if (code === "LT") currency = "EUR";
  
  if (!supported.includes(currency)) {
      currency = "USD";
  }
  
  const keywords = JSON.stringify([nameRus.toLowerCase(), nameEng.toLowerCase(), code.toLowerCase()]);
  result += `    { name: "${nameRus.replace(/"/g, '\\"')}", flag: "${flag}", code: "${code}", currency: "${currency}", keywords: ${keywords} },\n`;
}
result = result.replace(/,\n$/, "\n];\n");

const fs = require('fs');
fs.writeFileSync("countries_js.txt", result);
console.log("Done");
