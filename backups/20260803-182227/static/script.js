let currentCategory = 'donation';
let isTransitioning = false;

let projectLimits = { min_donation: 5, min_investment: 100 };
const exchangeRateCache = new Map();

const optionsData = [
    { category: 'donation', title: 'Анонимный взнос', min_amount_key: 'min_donation' },
    { category: 'donation', title: 'Персональный взнос', min_amount_key: 'min_donation' },
    { category: 'investment', title: 'Выбрать проект', min_amount_key: 'min_investment', project_id: '', placeholder: true }
];

async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        const data = await response.json();
        projectLimits.min_donation = parseFloat(data.min_donation) || 5;
        projectLimits.min_investment = parseFloat(data.min_investment) || 100;
        
        if (Array.isArray(data.projects)) {
            const projects = data.projects;
            optionsData.splice(2, optionsData.length - 2,
                { category: 'investment', title: 'Выбрать проект', min_amount_key: 'min_investment', project_id: '', placeholder: true },
                { category: 'investment', title: 'Предложить свой', min_amount_key: 'min_investment', project_id: '-1', custom: true },
                ...projects.map(p => ({
                    category: 'investment', title: p.name, min_amount_key: 'min_investment',
                    project_id: String(p.id), description: p.description || '', media_url: p.media_url || '',
                    min_amount: Number(p.min_amount) > 0 ? Number(p.min_amount) : null
                }))
            );
            if (currentCategory === 'investment') renderCustomDropdown();
        }

        // Update input validation
        const amountInput = document.getElementById('amountInput');
        if (amountInput) {
            updateMinAmountDisplay();
            amountInput.addEventListener('input', fetchExchangeRate);
        }
    } catch (e) {
        console.error("Failed to load config", e);
    }
}

// Load config when script runs
loadConfig();

// Country Dictionary with Flags & Currencies for Auto-selection
const countryDictionary = [
    { name: "Австралия", flag: "🇦🇺", code: "AU", currency: "USD", keywords: ["австралия","australia","au"] },
    { name: "Австрия", flag: "🇦🇹", code: "AT", currency: "EUR", keywords: ["австрия","austria","at"] },
    { name: "Азербайджан", flag: "🇦🇿", code: "AZ", currency: "AZN", keywords: ["азербайджан","azerbaijan","az"] },
    { name: "Аландские острова", flag: "🇦🇽", code: "AX", currency: "EUR", keywords: ["аландские острова","åland islands","ax"] },
    { name: "Албания", flag: "🇦🇱", code: "AL", currency: "USD", keywords: ["албания","albania","al"] },
    { name: "Алжир", flag: "🇩🇿", code: "DZ", currency: "USD", keywords: ["алжир","algeria","dz"] },
    { name: "Виргинские Острова (США)", flag: "🇻🇮", code: "VI", currency: "USD", keywords: ["виргинские острова (сша)","virgin islands, u.s.","vi"] },
    { name: "Американское Самоа", flag: "🇦🇸", code: "AS", currency: "USD", keywords: ["американское самоа","american samoa","as"] },
    { name: "Ангилья", flag: "🇦🇮", code: "AI", currency: "USD", keywords: ["ангилья","anguilla","ai"] },
    { name: "Ангола", flag: "🇦🇴", code: "AO", currency: "USD", keywords: ["ангола","angola","ao"] },
    { name: "Андорра", flag: "🇦🇩", code: "AD", currency: "EUR", keywords: ["андорра","andorra","ad"] },
    { name: "Антарктида", flag: "🇦🇶", code: "AQ", currency: "USD", keywords: ["антарктида","antarctica","aq"] },
    { name: "Антигуа и Барбуда", flag: "🇦🇬", code: "AG", currency: "USD", keywords: ["антигуа и барбуда","antigua and barbuda","ag"] },
    { name: "Аргентина", flag: "🇦🇷", code: "AR", currency: "USD", keywords: ["аргентина","argentina","ar"] },
    { name: "Армения", flag: "🇦🇲", code: "AM", currency: "USD", keywords: ["армения","armenia","am"] },
    { name: "Аруба", flag: "🇦🇼", code: "AW", currency: "USD", keywords: ["аруба","aruba","aw"] },
    { name: "Афганистан", flag: "🇦🇫", code: "AF", currency: "USD", keywords: ["афганистан","afghanistan","af"] },
    { name: "Багамы", flag: "🇧🇸", code: "BS", currency: "USD", keywords: ["багамы","bahamas","bs"] },
    { name: "Бангладеш", flag: "🇧🇩", code: "BD", currency: "USD", keywords: ["бангладеш","bangladesh","bd"] },
    { name: "Барбадос", flag: "🇧🇧", code: "BB", currency: "USD", keywords: ["барбадос","barbados","bb"] },
    { name: "Бахрейн", flag: "🇧🇭", code: "BH", currency: "USD", keywords: ["бахрейн","bahrain","bh"] },
    { name: "Белиз", flag: "🇧🇿", code: "BZ", currency: "USD", keywords: ["белиз","belize","bz"] },
    { name: "Беларусь", flag: "🇧🇾", code: "BY", currency: "RUB", keywords: ["беларусь","belarus","by"] },
    { name: "Бельгия", flag: "🇧🇪", code: "BE", currency: "EUR", keywords: ["бельгия","belgium","be"] },
    { name: "Бенин", flag: "🇧🇯", code: "BJ", currency: "USD", keywords: ["бенин","benin","bj"] },
    { name: "Бермуды", flag: "🇧🇲", code: "BM", currency: "USD", keywords: ["бермуды","bermuda","bm"] },
    { name: "Болгария", flag: "🇧🇬", code: "BG", currency: "USD", keywords: ["болгария","bulgaria","bg"] },
    { name: "Боливия", flag: "🇧🇴", code: "BO", currency: "USD", keywords: ["боливия","bolivia","bo"] },
    { name: "Бонэйр, Синт-Эстатиус и Саба", flag: "🇧🇶", code: "BQ", currency: "USD", keywords: ["бонэйр, синт-эстатиус и саба","bonaire, sint eustatius and saba","bq"] },
    { name: "Босния и Герцеговина", flag: "🇧🇦", code: "BA", currency: "USD", keywords: ["босния и герцеговина","bosnia and herzegovina","ba"] },
    { name: "Ботсвана", flag: "🇧🇼", code: "BW", currency: "USD", keywords: ["ботсвана","botswana","bw"] },
    { name: "Бразилия", flag: "🇧🇷", code: "BR", currency: "USD", keywords: ["бразилия","brazil","br"] },
    { name: "Британская территория в Индийском океане", flag: "🇮🇴", code: "IO", currency: "USD", keywords: ["британская территория в индийском океане","british indian ocean territory","io"] },
    { name: "Виргинские Острова (Великобритания)", flag: "🇻🇬", code: "VG", currency: "USD", keywords: ["виргинские острова (великобритания)","virgin islands, british","vg"] },
    { name: "Бруней", flag: "🇧🇳", code: "BN", currency: "USD", keywords: ["бруней","brunei darussalam","bn"] },
    { name: "Буркина-Фасо", flag: "🇧🇫", code: "BF", currency: "USD", keywords: ["буркина-фасо","burkina faso","bf"] },
    { name: "Бурунди", flag: "🇧🇮", code: "BI", currency: "USD", keywords: ["бурунди","burundi","bi"] },
    { name: "Бутан", flag: "🇧🇹", code: "BT", currency: "USD", keywords: ["бутан","bhutan","bt"] },
    { name: "Вануату", flag: "🇻🇺", code: "VU", currency: "USD", keywords: ["вануату","vanuatu","vu"] },
    { name: "Ватикан", flag: "🇻🇦", code: "VA", currency: "USD", keywords: ["ватикан","holy see (vatican city state)","va"] },
    { name: "Великобритания", flag: "🇬🇧", code: "GB", currency: "GBP", keywords: ["великобритания","united kingdom","gb"] },
    { name: "Венгрия", flag: "🇭🇺", code: "HU", currency: "USD", keywords: ["венгрия","hungary","hu"] },
    { name: "Венесуэла", flag: "🇻🇪", code: "VE", currency: "USD", keywords: ["венесуэла","venezuela","ve"] },
    { name: "Внешние малые острова (США)", flag: "🇺🇲", code: "UM", currency: "USD", keywords: ["внешние малые острова (сша)","united states minor outlying islands","um"] },
    { name: "Восточный Тимор", flag: "🇹🇱", code: "TL", currency: "USD", keywords: ["восточный тимор","timor-leste","tl"] },
    { name: "Вьетнам", flag: "🇻🇳", code: "VN", currency: "USD", keywords: ["вьетнам","vietnam","vn"] },
    { name: "Габон", flag: "🇬🇦", code: "GA", currency: "USD", keywords: ["габон","gabon","ga"] },
    { name: "Гаити", flag: "🇭🇹", code: "HT", currency: "USD", keywords: ["гаити","haiti","ht"] },
    { name: "Гайана", flag: "🇬🇾", code: "GY", currency: "USD", keywords: ["гайана","guyana","gy"] },
    { name: "Гамбия", flag: "🇬🇲", code: "GM", currency: "USD", keywords: ["гамбия","republic of the gambia","gm"] },
    { name: "Гана", flag: "🇬🇭", code: "GH", currency: "USD", keywords: ["гана","ghana","gh"] },
    { name: "Гваделупа", flag: "🇬🇵", code: "GP", currency: "EUR", keywords: ["гваделупа","guadeloupe","gp"] },
    { name: "Гватемала", flag: "🇬🇹", code: "GT", currency: "USD", keywords: ["гватемала","guatemala","gt"] },
    { name: "Гвиана", flag: "🇬🇫", code: "GF", currency: "EUR", keywords: ["гвиана","french guiana","gf"] },
    { name: "Гвинея", flag: "🇬🇳", code: "GN", currency: "USD", keywords: ["гвинея","guinea","gn"] },
    { name: "Гвинея-Бисау", flag: "🇬🇼", code: "GW", currency: "USD", keywords: ["гвинея-бисау","guinea-bissau","gw"] },
    { name: "Германия", flag: "🇩🇪", code: "DE", currency: "EUR", keywords: ["германия","germany","de"] },
    { name: "Гернси", flag: "🇬🇬", code: "GG", currency: "USD", keywords: ["гернси","guernsey","gg"] },
    { name: "Гибралтар", flag: "🇬🇮", code: "GI", currency: "USD", keywords: ["гибралтар","gibraltar","gi"] },
    { name: "Гондурас", flag: "🇭🇳", code: "HN", currency: "USD", keywords: ["гондурас","honduras","hn"] },
    { name: "Гонконг", flag: "🇭🇰", code: "HK", currency: "USD", keywords: ["гонконг","hong kong","hk"] },
    { name: "Гренада", flag: "🇬🇩", code: "GD", currency: "USD", keywords: ["гренада","grenada","gd"] },
    { name: "Гренландия", flag: "🇬🇱", code: "GL", currency: "USD", keywords: ["гренландия","greenland","gl"] },
    { name: "Греция", flag: "🇬🇷", code: "GR", currency: "EUR", keywords: ["греция","greece","gr"] },
    { name: "Грузия", flag: "🇬🇪", code: "GE", currency: "GEL", keywords: ["грузия","georgia","ge"] },
    { name: "Гуам", flag: "🇬🇺", code: "GU", currency: "USD", keywords: ["гуам","guam","gu"] },
    { name: "Дания", flag: "🇩🇰", code: "DK", currency: "USD", keywords: ["дания","denmark","dk"] },
    { name: "Джерси", flag: "🇯🇪", code: "JE", currency: "USD", keywords: ["джерси","jersey","je"] },
    { name: "Джибути", flag: "🇩🇯", code: "DJ", currency: "USD", keywords: ["джибути","djibouti","dj"] },
    { name: "Доминика", flag: "🇩🇲", code: "DM", currency: "USD", keywords: ["доминика","dominica","dm"] },
    { name: "Доминиканская Республика", flag: "🇩🇴", code: "DO", currency: "USD", keywords: ["доминиканская республика","dominican republic","do"] },
    { name: "Демократическая Республика Конго", flag: "🇨🇩", code: "CD", currency: "USD", keywords: ["демократическая республика конго","democratic republic of the congo","cd"] },
    { name: "Египет", flag: "🇪🇬", code: "EG", currency: "USD", keywords: ["египет","egypt","eg"] },
    { name: "Замбия", flag: "🇿🇲", code: "ZM", currency: "USD", keywords: ["замбия","zambia","zm"] },
    { name: "САДР", flag: "🇪🇭", code: "EH", currency: "USD", keywords: ["садр","western sahara","eh"] },
    { name: "Зимбабве", flag: "🇿🇼", code: "ZW", currency: "USD", keywords: ["зимбабве","zimbabwe","zw"] },
    { name: "Израиль", flag: "🇮🇱", code: "IL", currency: "USD", keywords: ["израиль","israel","il"] },
    { name: "Индия", flag: "🇮🇳", code: "IN", currency: "USD", keywords: ["индия","india","in"] },
    { name: "Индонезия", flag: "🇮🇩", code: "ID", currency: "USD", keywords: ["индонезия","indonesia","id"] },
    { name: "Иордания", flag: "🇯🇴", code: "JO", currency: "USD", keywords: ["иордания","jordan","jo"] },
    { name: "Ирак", flag: "🇮🇶", code: "IQ", currency: "USD", keywords: ["ирак","iraq","iq"] },
    { name: "Иран", flag: "🇮🇷", code: "IR", currency: "USD", keywords: ["иран","islamic republic of iran","ir"] },
    { name: "Ирландия", flag: "🇮🇪", code: "IE", currency: "EUR", keywords: ["ирландия","ireland","ie"] },
    { name: "Исландия", flag: "🇮🇸", code: "IS", currency: "USD", keywords: ["исландия","iceland","is"] },
    { name: "Испания", flag: "🇪🇸", code: "ES", currency: "EUR", keywords: ["испания","spain","es"] },
    { name: "Италия", flag: "🇮🇹", code: "IT", currency: "EUR", keywords: ["италия","italy","it"] },
    { name: "Йемен", flag: "🇾🇪", code: "YE", currency: "USD", keywords: ["йемен","yemen","ye"] },
    { name: "Кабо-Верде", flag: "🇨🇻", code: "CV", currency: "USD", keywords: ["кабо-верде","cape verde","cv"] },
    { name: "Казахстан", flag: "🇰🇿", code: "KZ", currency: "KZT", keywords: ["казахстан","kazakhstan","kz"] },
    { name: "Острова Кайман", flag: "🇰🇾", code: "KY", currency: "USD", keywords: ["острова кайман","cayman islands","ky"] },
    { name: "Камбоджа", flag: "🇰🇭", code: "KH", currency: "USD", keywords: ["камбоджа","cambodia","kh"] },
    { name: "Камерун", flag: "🇨🇲", code: "CM", currency: "USD", keywords: ["камерун","cameroon","cm"] },
    { name: "Канада", flag: "🇨🇦", code: "CA", currency: "USD", keywords: ["канада","canada","ca"] },
    { name: "Катар", flag: "🇶🇦", code: "QA", currency: "USD", keywords: ["катар","qatar","qa"] },
    { name: "Кения", flag: "🇰🇪", code: "KE", currency: "USD", keywords: ["кения","kenya","ke"] },
    { name: "Кипр", flag: "🇨🇾", code: "CY", currency: "EUR", keywords: ["кипр","cyprus","cy"] },
    { name: "Киргизия", flag: "🇰🇬", code: "KG", currency: "USD", keywords: ["киргизия","kyrgyzstan","kg"] },
    { name: "Кирибати", flag: "🇰🇮", code: "KI", currency: "USD", keywords: ["кирибати","kiribati","ki"] },
    { name: "Тайвань", flag: "🇹🇼", code: "TW", currency: "USD", keywords: ["тайвань","taiwan, province of china","tw"] },
    { name: "КНДР (Корейская Народно-Демократическая Республика)", flag: "🇰🇵", code: "KP", currency: "USD", keywords: ["кндр (корейская народно-демократическая республика)","north korea","kp"] },
    { name: "КНР (Китайская Народная Республика)", flag: "🇨🇳", code: "CN", currency: "USD", keywords: ["кнр (китайская народная республика)","people's republic of china","cn"] },
    { name: "Кокосовые острова", flag: "🇨🇨", code: "CC", currency: "USD", keywords: ["кокосовые острова","cocos (keeling) islands","cc"] },
    { name: "Колумбия", flag: "🇨🇴", code: "CO", currency: "USD", keywords: ["колумбия","colombia","co"] },
    { name: "Коморы", flag: "🇰🇲", code: "KM", currency: "USD", keywords: ["коморы","comoros","km"] },
    { name: "Коста-Рика", flag: "🇨🇷", code: "CR", currency: "USD", keywords: ["коста-рика","costa rica","cr"] },
    { name: "Кот-д’Ивуар", flag: "🇨🇮", code: "CI", currency: "USD", keywords: ["кот-д’ивуар","cote d'ivoire","ci"] },
    { name: "Куба", flag: "🇨🇺", code: "CU", currency: "USD", keywords: ["куба","cuba","cu"] },
    { name: "Кувейт", flag: "🇰🇼", code: "KW", currency: "USD", keywords: ["кувейт","kuwait","kw"] },
    { name: "Кюрасао", flag: "🇨🇼", code: "CW", currency: "USD", keywords: ["кюрасао","curaçao","cw"] },
    { name: "Лаос", flag: "🇱🇦", code: "LA", currency: "USD", keywords: ["лаос","lao people's democratic republic","la"] },
    { name: "Латвия", flag: "🇱🇻", code: "LV", currency: "EUR", keywords: ["латвия","latvia","lv"] },
    { name: "Лесото", flag: "🇱🇸", code: "LS", currency: "USD", keywords: ["лесото","lesotho","ls"] },
    { name: "Либерия", flag: "🇱🇷", code: "LR", currency: "USD", keywords: ["либерия","liberia","lr"] },
    { name: "Ливан", flag: "🇱🇧", code: "LB", currency: "USD", keywords: ["ливан","lebanon","lb"] },
    { name: "Ливия", flag: "🇱🇾", code: "LY", currency: "USD", keywords: ["ливия","libya","ly"] },
    { name: "Литва", flag: "🇱🇹", code: "LT", currency: "EUR", keywords: ["литва","lithuania","lt"] },
    { name: "Лихтенштейн", flag: "🇱🇮", code: "LI", currency: "USD", keywords: ["лихтенштейн","liechtenstein","li"] },
    { name: "Люксембург", flag: "🇱🇺", code: "LU", currency: "EUR", keywords: ["люксембург","luxembourg","lu"] },
    { name: "Маврикий", flag: "🇲🇺", code: "MU", currency: "USD", keywords: ["маврикий","mauritius","mu"] },
    { name: "Мавритания", flag: "🇲🇷", code: "MR", currency: "USD", keywords: ["мавритания","mauritania","mr"] },
    { name: "Мадагаскар", flag: "🇲🇬", code: "MG", currency: "USD", keywords: ["мадагаскар","madagascar","mg"] },
    { name: "Майотта", flag: "🇾🇹", code: "YT", currency: "EUR", keywords: ["майотта","mayotte","yt"] },
    { name: "Макао", flag: "🇲🇴", code: "MO", currency: "USD", keywords: ["макао","macao","mo"] },
    { name: "Малави", flag: "🇲🇼", code: "MW", currency: "USD", keywords: ["малави","malawi","mw"] },
    { name: "Малайзия", flag: "🇲🇾", code: "MY", currency: "USD", keywords: ["малайзия","malaysia","my"] },
    { name: "Мали", flag: "🇲🇱", code: "ML", currency: "USD", keywords: ["мали","mali","ml"] },
    { name: "Мальдивы", flag: "🇲🇻", code: "MV", currency: "USD", keywords: ["мальдивы","maldives","mv"] },
    { name: "Мальта", flag: "🇲🇹", code: "MT", currency: "EUR", keywords: ["мальта","malta","mt"] },
    { name: "Марокко", flag: "🇲🇦", code: "MA", currency: "USD", keywords: ["марокко","morocco","ma"] },
    { name: "Мартиника", flag: "🇲🇶", code: "MQ", currency: "EUR", keywords: ["мартиника","martinique","mq"] },
    { name: "Маршалловы Острова", flag: "🇲🇭", code: "MH", currency: "USD", keywords: ["маршалловы острова","marshall islands","mh"] },
    { name: "Мексика", flag: "🇲🇽", code: "MX", currency: "USD", keywords: ["мексика","mexico","mx"] },
    { name: "Микронезия", flag: "🇫🇲", code: "FM", currency: "USD", keywords: ["микронезия","micronesia, federated states of","fm"] },
    { name: "Мозамбик", flag: "🇲🇿", code: "MZ", currency: "USD", keywords: ["мозамбик","mozambique","mz"] },
    { name: "Молдавия", flag: "🇲🇩", code: "MD", currency: "USD", keywords: ["молдавия","moldova, republic of","md"] },
    { name: "Монако", flag: "🇲🇨", code: "MC", currency: "EUR", keywords: ["монако","monaco","mc"] },
    { name: "Монголия", flag: "🇲🇳", code: "MN", currency: "USD", keywords: ["монголия","mongolia","mn"] },
    { name: "Монтсеррат", flag: "🇲🇸", code: "MS", currency: "USD", keywords: ["монтсеррат","montserrat","ms"] },
    { name: "Мьянма", flag: "🇲🇲", code: "MM", currency: "USD", keywords: ["мьянма","myanmar","mm"] },
    { name: "Намибия", flag: "🇳🇦", code: "NA", currency: "USD", keywords: ["намибия","namibia","na"] },
    { name: "Науру", flag: "🇳🇷", code: "NR", currency: "USD", keywords: ["науру","nauru","nr"] },
    { name: "Непал", flag: "🇳🇵", code: "NP", currency: "USD", keywords: ["непал","nepal","np"] },
    { name: "Нигер", flag: "🇳🇪", code: "NE", currency: "USD", keywords: ["нигер","niger","ne"] },
    { name: "Нигерия", flag: "🇳🇬", code: "NG", currency: "USD", keywords: ["нигерия","nigeria","ng"] },
    { name: "Нидерланды", flag: "🇳🇱", code: "NL", currency: "EUR", keywords: ["нидерланды","netherlands","nl"] },
    { name: "Никарагуа", flag: "🇳🇮", code: "NI", currency: "USD", keywords: ["никарагуа","nicaragua","ni"] },
    { name: "Ниуэ", flag: "🇳🇺", code: "NU", currency: "USD", keywords: ["ниуэ","niue","nu"] },
    { name: "Новая Зеландия", flag: "🇳🇿", code: "NZ", currency: "USD", keywords: ["новая зеландия","new zealand","nz"] },
    { name: "Новая Каледония", flag: "🇳🇨", code: "NC", currency: "USD", keywords: ["новая каледония","new caledonia","nc"] },
    { name: "Норвегия", flag: "🇳🇴", code: "NO", currency: "USD", keywords: ["норвегия","norway","no"] },
    { name: "ОАЭ", flag: "🇦🇪", code: "AE", currency: "USD", keywords: ["оаэ","united arab emirates","ae"] },
    { name: "Оман", flag: "🇴🇲", code: "OM", currency: "USD", keywords: ["оман","oman","om"] },
    { name: "Остров Буве", flag: "🇧🇻", code: "BV", currency: "USD", keywords: ["остров буве","bouvet island","bv"] },
    { name: "Остров Мэн", flag: "🇮🇲", code: "IM", currency: "USD", keywords: ["остров мэн","isle of man","im"] },
    { name: "Острова Кука", flag: "🇨🇰", code: "CK", currency: "USD", keywords: ["острова кука","cook islands","ck"] },
    { name: "Остров Норфолк", flag: "🇳🇫", code: "NF", currency: "USD", keywords: ["остров норфолк","norfolk island","nf"] },
    { name: "Остров Рождества", flag: "🇨🇽", code: "CX", currency: "USD", keywords: ["остров рождества","christmas island","cx"] },
    { name: "Острова Питкэрн", flag: "🇵🇳", code: "PN", currency: "USD", keywords: ["острова питкэрн","pitcairn","pn"] },
    { name: "Острова Святой Елены, Вознесения и Тристан-да-Кунья", flag: "🇸🇭", code: "SH", currency: "USD", keywords: ["острова святой елены, вознесения и тристан-да-кунья","saint helena","sh"] },
    { name: "Пакистан", flag: "🇵🇰", code: "PK", currency: "USD", keywords: ["пакистан","pakistan","pk"] },
    { name: "Палау", flag: "🇵🇼", code: "PW", currency: "USD", keywords: ["палау","palau","pw"] },
    { name: "Государство Палестина", flag: "🇵🇸", code: "PS", currency: "USD", keywords: ["государство палестина","state of palestine","ps"] },
    { name: "Панама", flag: "🇵🇦", code: "PA", currency: "USD", keywords: ["панама","panama","pa"] },
    { name: "Папуа — Новая Гвинея", flag: "🇵🇬", code: "PG", currency: "USD", keywords: ["папуа — новая гвинея","papua new guinea","pg"] },
    { name: "Парагвай", flag: "🇵🇾", code: "PY", currency: "USD", keywords: ["парагвай","paraguay","py"] },
    { name: "Перу", flag: "🇵🇪", code: "PE", currency: "USD", keywords: ["перу","peru","pe"] },
    { name: "Польша", flag: "🇵🇱", code: "PL", currency: "PLN", keywords: ["польша","poland","pl"] },
    { name: "Португалия", flag: "🇵🇹", code: "PT", currency: "EUR", keywords: ["португалия","portugal","pt"] },
    { name: "Пуэрто-Рико", flag: "🇵🇷", code: "PR", currency: "USD", keywords: ["пуэрто-рико","puerto rico","pr"] },
    { name: "Республика Конго", flag: "🇨🇬", code: "CG", currency: "USD", keywords: ["республика конго","republic of the congo","cg"] },
    { name: "Республика Корея", flag: "🇰🇷", code: "KR", currency: "USD", keywords: ["республика корея","south korea","kr"] },
    { name: "Реюньон", flag: "🇷🇪", code: "RE", currency: "USD", keywords: ["реюньон","reunion","re"] },
    { name: "Российская Федерация", flag: "🇷🇺", code: "RU", currency: "RUB", keywords: ["российская федерация","russian federation","ru"] },
    { name: "Руанда", flag: "🇷🇼", code: "RW", currency: "USD", keywords: ["руанда","rwanda","rw"] },
    { name: "Румыния", flag: "🇷🇴", code: "RO", currency: "USD", keywords: ["румыния","romania","ro"] },
    { name: "Сальвадор", flag: "🇸🇻", code: "SV", currency: "USD", keywords: ["сальвадор","el salvador","sv"] },
    { name: "Самоа", flag: "🇼🇸", code: "WS", currency: "USD", keywords: ["самоа","samoa","ws"] },
    { name: "Сан-Марино", flag: "🇸🇲", code: "SM", currency: "EUR", keywords: ["сан-марино","san marino","sm"] },
    { name: "Сан-Томе и Принсипи", flag: "🇸🇹", code: "ST", currency: "USD", keywords: ["сан-томе и принсипи","sao tome and principe","st"] },
    { name: "Саудовская Аравия", flag: "🇸🇦", code: "SA", currency: "USD", keywords: ["саудовская аравия","saudi arabia","sa"] },
    { name: "Эсватини", flag: "🇸🇿", code: "SZ", currency: "USD", keywords: ["эсватини","eswatini","sz"] },
    { name: "Северная Македония", flag: "🇲🇰", code: "MK", currency: "USD", keywords: ["северная македония","the republic of north macedonia","mk"] },
    { name: "Северные Марианские Острова", flag: "🇲🇵", code: "MP", currency: "USD", keywords: ["северные марианские острова","northern mariana islands","mp"] },
    { name: "Сейшельские Острова", flag: "🇸🇨", code: "SC", currency: "USD", keywords: ["сейшельские острова","seychelles","sc"] },
    { name: "Сен-Бартелеми", flag: "🇧🇱", code: "BL", currency: "EUR", keywords: ["сен-бартелеми","saint barthélemy","bl"] },
    { name: "Сен-Мартен", flag: "🇲🇫", code: "MF", currency: "EUR", keywords: ["сен-мартен","saint martin (french part)","mf"] },
    { name: "Сен-Пьер и Микелон", flag: "🇵🇲", code: "PM", currency: "EUR", keywords: ["сен-пьер и микелон","saint pierre and miquelon","pm"] },
    { name: "Сенегал", flag: "🇸🇳", code: "SN", currency: "USD", keywords: ["сенегал","senegal","sn"] },
    { name: "Сент-Винсент и Гренадины", flag: "🇻🇨", code: "VC", currency: "USD", keywords: ["сент-винсент и гренадины","saint vincent and the grenadines","vc"] },
    { name: "Сент-Китс и Невис", flag: "🇰🇳", code: "KN", currency: "USD", keywords: ["сент-китс и невис","saint kitts and nevis","kn"] },
    { name: "Сент-Люсия", flag: "🇱🇨", code: "LC", currency: "USD", keywords: ["сент-люсия","saint lucia","lc"] },
    { name: "Сербия", flag: "🇷🇸", code: "RS", currency: "USD", keywords: ["сербия","serbia","rs"] },
    { name: "Сингапур", flag: "🇸🇬", code: "SG", currency: "USD", keywords: ["сингапур","singapore","sg"] },
    { name: "Синт-Мартен", flag: "🇸🇽", code: "SX", currency: "USD", keywords: ["синт-мартен","sint maarten (dutch part)","sx"] },
    { name: "Сирия", flag: "🇸🇾", code: "SY", currency: "USD", keywords: ["сирия","syrian arab republic","sy"] },
    { name: "Словакия", flag: "🇸🇰", code: "SK", currency: "EUR", keywords: ["словакия","slovakia","sk"] },
    { name: "Словения", flag: "🇸🇮", code: "SI", currency: "EUR", keywords: ["словения","slovenia","si"] },
    { name: "Соломоновы Острова", flag: "🇸🇧", code: "SB", currency: "USD", keywords: ["соломоновы острова","solomon islands","sb"] },
    { name: "Сомали", flag: "🇸🇴", code: "SO", currency: "USD", keywords: ["сомали","somalia","so"] },
    { name: "Судан", flag: "🇸🇩", code: "SD", currency: "USD", keywords: ["судан","sudan","sd"] },
    { name: "Суринам", flag: "🇸🇷", code: "SR", currency: "USD", keywords: ["суринам","suriname","sr"] },
    { name: "США", flag: "🇺🇸", code: "US", currency: "USD", keywords: ["сша","united states of america","us"] },
    { name: "Сьерра-Леоне", flag: "🇸🇱", code: "SL", currency: "USD", keywords: ["сьерра-леоне","sierra leone","sl"] },
    { name: "Таджикистан", flag: "🇹🇯", code: "TJ", currency: "USD", keywords: ["таджикистан","tajikistan","tj"] },
    { name: "Таиланд", flag: "🇹🇭", code: "TH", currency: "USD", keywords: ["таиланд","thailand","th"] },
    { name: "Танзания", flag: "🇹🇿", code: "TZ", currency: "USD", keywords: ["танзания","united republic of tanzania","tz"] },
    { name: "Теркс и Кайкос", flag: "🇹🇨", code: "TC", currency: "USD", keywords: ["теркс и кайкос","turks and caicos islands","tc"] },
    { name: "Того", flag: "🇹🇬", code: "TG", currency: "USD", keywords: ["того","togo","tg"] },
    { name: "Токелау", flag: "🇹🇰", code: "TK", currency: "USD", keywords: ["токелау","tokelau","tk"] },
    { name: "Тонга", flag: "🇹🇴", code: "TO", currency: "USD", keywords: ["тонга","tonga","to"] },
    { name: "Тринидад и Тобаго", flag: "🇹🇹", code: "TT", currency: "USD", keywords: ["тринидад и тобаго","trinidad and tobago","tt"] },
    { name: "Тувалу", flag: "🇹🇻", code: "TV", currency: "USD", keywords: ["тувалу","tuvalu","tv"] },
    { name: "Тунис", flag: "🇹🇳", code: "TN", currency: "USD", keywords: ["тунис","tunisia","tn"] },
    { name: "Туркмения", flag: "🇹🇲", code: "TM", currency: "USD", keywords: ["туркмения","turkmenistan","tm"] },
    { name: "Турция", flag: "🇹🇷", code: "TR", currency: "USD", keywords: ["турция","türkiye","tr"] },
    { name: "Уганда", flag: "🇺🇬", code: "UG", currency: "USD", keywords: ["уганда","uganda","ug"] },
    { name: "Узбекистан", flag: "🇺🇿", code: "UZ", currency: "USD", keywords: ["узбекистан","uzbekistan","uz"] },
    { name: "Украина", flag: "🇺🇦", code: "UA", currency: "UAH", keywords: ["украина","ukraine","ua"] },
    { name: "Уоллис и Футуна", flag: "🇼🇫", code: "WF", currency: "USD", keywords: ["уоллис и футуна","wallis and futuna","wf"] },
    { name: "Уругвай", flag: "🇺🇾", code: "UY", currency: "USD", keywords: ["уругвай","uruguay","uy"] },
    { name: "Фареры", flag: "🇫🇴", code: "FO", currency: "USD", keywords: ["фареры","faroe islands","fo"] },
    { name: "Фиджи", flag: "🇫🇯", code: "FJ", currency: "USD", keywords: ["фиджи","fiji","fj"] },
    { name: "Филиппины", flag: "🇵🇭", code: "PH", currency: "USD", keywords: ["филиппины","philippines","ph"] },
    { name: "Финляндия", flag: "🇫🇮", code: "FI", currency: "EUR", keywords: ["финляндия","finland","fi"] },
    { name: "Фолклендские острова", flag: "🇫🇰", code: "FK", currency: "USD", keywords: ["фолклендские острова","falkland islands (malvinas)","fk"] },
    { name: "Франция", flag: "🇫🇷", code: "FR", currency: "EUR", keywords: ["франция","france","fr"] },
    { name: "Французская Полинезия", flag: "🇵🇫", code: "PF", currency: "USD", keywords: ["французская полинезия","french polynesia","pf"] },
    { name: "Французские Южные и Антарктические Территории", flag: "🇹🇫", code: "TF", currency: "USD", keywords: ["французские южные и антарктические территории","french southern territories","tf"] },
    { name: "Херд и Макдональд", flag: "🇭🇲", code: "HM", currency: "USD", keywords: ["херд и макдональд","heard island and mcdonald islands","hm"] },
    { name: "Хорватия", flag: "🇭🇷", code: "HR", currency: "EUR", keywords: ["хорватия","croatia","hr"] },
    { name: "ЦАР", flag: "🇨🇫", code: "CF", currency: "USD", keywords: ["цар","central african republic","cf"] },
    { name: "Чад", flag: "🇹🇩", code: "TD", currency: "USD", keywords: ["чад","chad","td"] },
    { name: "Черногория", flag: "🇲🇪", code: "ME", currency: "EUR", keywords: ["черногория","montenegro","me"] },
    { name: "Чехия", flag: "🇨🇿", code: "CZ", currency: "USD", keywords: ["чехия","czech republic","cz"] },
    { name: "Чили", flag: "🇨🇱", code: "CL", currency: "USD", keywords: ["чили","chile","cl"] },
    { name: "Швейцария", flag: "🇨🇭", code: "CH", currency: "USD", keywords: ["швейцария","switzerland","ch"] },
    { name: "Швеция", flag: "🇸🇪", code: "SE", currency: "USD", keywords: ["швеция","sweden","se"] },
    { name: "Шпицберген и Ян-Майен", flag: "🇸🇯", code: "SJ", currency: "USD", keywords: ["шпицберген и ян-майен","svalbard and jan mayen","sj"] },
    { name: "Шри-Ланка", flag: "🇱🇰", code: "LK", currency: "USD", keywords: ["шри-ланка","sri lanka","lk"] },
    { name: "Эквадор", flag: "🇪🇨", code: "EC", currency: "USD", keywords: ["эквадор","ecuador","ec"] },
    { name: "Экваториальная Гвинея", flag: "🇬🇶", code: "GQ", currency: "USD", keywords: ["экваториальная гвинея","equatorial guinea","gq"] },
    { name: "Эритрея", flag: "🇪🇷", code: "ER", currency: "USD", keywords: ["эритрея","eritrea","er"] },
    { name: "Эстония", flag: "🇪🇪", code: "EE", currency: "EUR", keywords: ["эстония","estonia","ee"] },
    { name: "Эфиопия", flag: "🇪🇹", code: "ET", currency: "USD", keywords: ["эфиопия","ethiopia","et"] },
    { name: "ЮАР", flag: "🇿🇦", code: "ZA", currency: "USD", keywords: ["юар","south africa","za"] },
    { name: "Южная Георгия и Южные Сандвичевы Острова", flag: "🇬🇸", code: "GS", currency: "USD", keywords: ["южная георгия и южные сандвичевы острова","south georgia and the south sandwich islands","gs"] },
    { name: "Южный Судан", flag: "🇸🇸", code: "SS", currency: "USD", keywords: ["южный судан","south sudan","ss"] },
    { name: "Ямайка", flag: "🇯🇲", code: "JM", currency: "USD", keywords: ["ямайка","jamaica","jm"] },
    { name: "Япония", flag: "🇯🇵", code: "JP", currency: "USD", keywords: ["япония","japan","jp"] },
    { name: "Косово", flag: "🇽🇰", code: "XK", currency: "USD", keywords: ["косово","kosovo","xk"] }
];


const countryCurrencyByCode = Object.freeze({"AQ":"USD","FM":"USD","BV":"NOK","HM":"AUD","AW":"AWG","AF":"AFN","AO":"AOA","AI":"XCD","AX":"EUR","AL":"ALL","AD":"EUR","AE":"AED","AR":"ARS","AM":"AMD","AS":"USD","TF":"EUR","AG":"XCD","AU":"AUD","AT":"EUR","AZ":"AZN","BI":"BIF","BE":"EUR","BJ":"XOF","BF":"XOF","BD":"BDT","BG":"EUR","BH":"BHD","BS":"BSD","BA":"BAM","BL":"EUR","SH":"GBP","BY":"BYN","BZ":"BZD","BM":"BMD","BO":"BOB","BQ":"USD","BR":"BRL","BB":"BBD","BN":"BND","BT":"BTN","BW":"BWP","CF":"XAF","CA":"CAD","CC":"AUD","CH":"CHF","CL":"CLP","CN":"CNY","CI":"XOF","CM":"XAF","CD":"CDF","CG":"XAF","CK":"NZD","CO":"COP","KM":"KMF","CV":"CVE","CR":"CRC","CU":"CUP","CW":"ANG","CX":"AUD","KY":"KYD","CY":"EUR","CZ":"CZK","DE":"EUR","DJ":"DJF","DM":"XCD","DK":"DKK","DO":"DOP","DZ":"DZD","EC":"USD","EG":"EGP","ER":"ERN","EH":"DZD","ES":"EUR","EE":"EUR","ET":"ETB","FI":"EUR","FJ":"FJD","FK":"FKP","FR":"EUR","FO":"DKK","GA":"XAF","GB":"GBP","GE":"GEL","GG":"GBP","GH":"GHS","GI":"GIP","GN":"GNF","GP":"EUR","GM":"GMD","GW":"XOF","GQ":"XAF","GR":"EUR","GD":"XCD","GL":"DKK","GT":"GTQ","GF":"EUR","GU":"USD","GY":"GYD","HK":"HKD","HN":"HNL","HR":"EUR","HT":"HTG","HU":"HUF","ID":"IDR","IM":"GBP","IN":"INR","IO":"USD","IE":"EUR","IR":"IRR","IQ":"IQD","IS":"ISK","IL":"ILS","IT":"EUR","JM":"JMD","JE":"GBP","JO":"JOD","JP":"JPY","KZ":"KZT","KE":"KES","KG":"KGS","KH":"KHR","KI":"AUD","KN":"XCD","KR":"KRW","XK":"EUR","KW":"KWD","LA":"LAK","LB":"LBP","LR":"LRD","LY":"LYD","LC":"XCD","LI":"CHF","LK":"LKR","LS":"LSL","LT":"EUR","LU":"EUR","LV":"EUR","MO":"MOP","MF":"EUR","MA":"MAD","MC":"EUR","MD":"MDL","MG":"MGA","MV":"MVR","MX":"MXN","MH":"USD","MK":"MKD","ML":"XOF","MT":"EUR","MM":"MMK","ME":"EUR","MN":"MNT","MP":"USD","MZ":"MZN","MR":"MRU","MS":"XCD","MQ":"EUR","MU":"MUR","MW":"MWK","MY":"MYR","YT":"EUR","NA":"NAD","NC":"XPF","NE":"XOF","NF":"AUD","NG":"NGN","NI":"NIO","NU":"NZD","NL":"EUR","NO":"NOK","NP":"NPR","NR":"AUD","NZ":"NZD","OM":"OMR","PK":"PKR","PA":"PAB","PN":"NZD","PE":"PEN","PH":"PHP","PW":"USD","PG":"PGK","PL":"PLN","PR":"USD","KP":"KPW","PT":"EUR","PY":"PYG","PS":"EGP","PF":"XPF","QA":"QAR","RE":"EUR","RO":"RON","RU":"RUB","RW":"RWF","SA":"SAR","SD":"SDG","SN":"XOF","SG":"SGD","GS":"SHP","SJ":"NOK","SB":"SBD","SL":"SLE","SV":"USD","SM":"EUR","SO":"SOS","PM":"EUR","RS":"RSD","SS":"SSP","ST":"STN","SR":"SRD","SK":"EUR","SI":"EUR","SE":"SEK","SZ":"SZL","SX":"ANG","SC":"SCR","SY":"SYP","TC":"USD","TD":"XAF","TG":"XOF","TH":"THB","TJ":"TJS","TK":"NZD","TM":"TMT","TL":"USD","TO":"TOP","TT":"TTD","TN":"TND","TR":"TRY","TV":"AUD","TW":"TWD","TZ":"TZS","UG":"UGX","UA":"UAH","UM":"USD","UY":"UYU","US":"USD","UZ":"UZS","VA":"EUR","VC":"XCD","VE":"VES","VG":"USD","VI":"USD","VN":"VND","VU":"VUV","WF":"XPF","WS":"WST","YE":"YER","ZA":"ZAR","ZM":"ZMW","ZW":"BWP"});

const contactPresets = [
    { type: "Telegram", prefix: "Telegram: @", placeholder: "@username" },
    { type: "WhatsApp", prefix: "WhatsApp: +", placeholder: "+380... / +48..." },
    { type: "GSM", prefix: "GSM: ", placeholder: "+48..." },
    { type: "IMO / LINE", prefix: "IMO/LINE: ", placeholder: "Ник или номер" },
    { type: "Email", prefix: "Email: ", placeholder: "example@domain.com" },
    { type: "Max", prefix: "Max: ", placeholder: "Российский мессенджер" }
];

// Canvas Particle System Initialization
const canvas = document.getElementById('grid-canvas');
const ctx = canvas.getContext('2d');
const glow = document.getElementById('bg-glow');
let mouseX = -1000, mouseY = -1000;
let isMobile = window.innerWidth < 768;

const numParticles = isMobile ? 22 : 48;
const particles = [];
for (let i = 0; i < numParticles; i++) {
    particles.push({
        x: Math.random() * window.innerWidth,
        y: Math.random() * window.innerHeight,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.35
    });
}

function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    isMobile = window.innerWidth < 768;
}

window.addEventListener('resize', resizeCanvas, { passive: true });
resizeCanvas();

if (!isMobile) {
    document.addEventListener('mousemove', (e) => {
        mouseX = e.clientX;
        mouseY = e.clientY;
        if (glow) {
            glow.style.left = mouseX + 'px';
            glow.style.top = mouseY + 'px';
        }
    }, { passive: true });
}

function drawMolecular() {
    if (document.hidden) {
        requestAnimationFrame(drawMolecular);
        return;
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const accentColorStr = getComputedStyle(document.body).getPropertyValue('--accent-glow').trim() || '#D4AF37';
    const maxConnectDist = isMobile ? 60 : 80;

    for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        p.x += p.vx;
        p.y += p.vy;

        if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
        if (p.y < 0 || p.y > canvas.height) p.vy *= -1;

        ctx.beginPath();
        ctx.arc(p.x, p.y, isMobile ? 1.0 : 1.2, 0, Math.PI * 2);
        ctx.fillStyle = accentColorStr;
        ctx.globalAlpha = 0.45;
        ctx.fill();

        for (let j = i + 1; j < particles.length; j++) {
            const p2 = particles[j];
            const ddx = p2.x - p.x;
            const ddy = p2.y - p.y;
            const ddistSq = ddx * ddx + ddy * ddy;

            if (ddistSq < maxConnectDist * maxConnectDist) {
                const ddist = Math.sqrt(ddistSq);
                ctx.beginPath();
                ctx.moveTo(p.x, p.y);
                ctx.lineTo(p2.x, p2.y);
                ctx.strokeStyle = accentColorStr;
                ctx.globalAlpha = 0.25 * (1 - ddist / maxConnectDist);
                ctx.lineWidth = 0.6;
                ctx.stroke();
            }
        }
    }

    requestAnimationFrame(drawMolecular);
}
drawMolecular();

// App Initialization
document.addEventListener("DOMContentLoaded", () => {
    renderCustomDropdown();
    switchCategory('donation'); // Default to donation
    
    document.addEventListener("click", (e) => {
        const dropdown = document.getElementById("customDropdown");
        if (dropdown && !dropdown.contains(e.target)) {
            dropdown.classList.remove("open");
            const pg = dropdown.closest(".form-group");
            if (pg) pg.style.zIndex = "50";
        }

        const countryBox = document.getElementById("countrySuggestions");
        const countryInput = document.getElementById("countryInput");
        if (countryBox && countryInput && !countryBox.contains(e.target) && e.target !== countryInput) {
            countryBox.style.display = "none";
        }

        const contactBox = document.getElementById("contactSuggestions");
        const contactInput = document.getElementById("contactInput");
        if (contactBox && contactInput && !contactBox.contains(e.target) && e.target !== contactInput) {
            contactBox.style.display = "none";
        }
    });

    const tabDonat = document.getElementById('tabDonation');
    const tabInvest = document.getElementById('tabInvestment');
    const pill = document.getElementById('tabPill');

    if (tabInvest && tabDonat && pill) {
        tabInvest.addEventListener('mouseenter', () => {
            if (currentCategory === 'donation' && !isTransitioning) pill.style.transform = 'translateX(12%)';
        });
        tabInvest.addEventListener('mouseleave', () => {
            if (currentCategory === 'donation' && !isTransitioning) pill.style.transform = 'translateX(0)';
        });
        tabDonat.addEventListener('mouseenter', () => {
            if (currentCategory === 'investment' && !isTransitioning) pill.style.transform = 'translateX(88%)';
        });
        tabDonat.addEventListener('mouseleave', () => {
            if (currentCategory === 'investment' && !isTransitioning) pill.style.transform = 'translateX(100%)';
        });
    }
});

function switchCategory(cat) {
    if (isTransitioning) return;
    isTransitioning = true;
    currentCategory = cat;

    document.body.className = `theme-${cat}`;
    const pill = document.getElementById('tabPill');
    if (pill) pill.style.transform = cat === 'donation' ? 'translateX(0)' : 'translateX(100%)';

    document.getElementById('tabDonation').classList.toggle('active', cat === 'donation');
    document.getElementById('tabInvestment').classList.toggle('active', cat === 'investment');

    const wrapper = document.getElementById('formWrapper');
    if (wrapper) wrapper.style.opacity = '0.3';
    
    setTimeout(() => {
        const amountLabel = document.getElementById('amountLabelText');
        const commentLabel = document.getElementById('commentLabelText');
        const contactInput = document.getElementById('contactInput');
        const contactReqNote = document.getElementById('contactReqNote');
        const feedbackCheckbox = document.getElementById('feedbackCheckbox');
        const feedbackReqNote = document.getElementById('feedbackReqNote');

        if (cat === 'donation') {
            if (amountLabel) amountLabel.innerText = 'Сумма доната €';
            if (commentLabel) commentLabel.innerHTML = 'Комментарий <span class="field-req-note">(необязательно)</span>';
            if (contactInput) {
                contactInput.required = false;
                if (contactReqNote) contactReqNote.innerText = '(необязательно)';
            }
            if (feedbackCheckbox) {
                feedbackCheckbox.required = false;
                feedbackCheckbox.checked = false;
                if (feedbackReqNote) feedbackReqNote.innerText = '(необязательно)';
            }
        } else { // Investor mode
            if (amountLabel) amountLabel.innerText = 'Сумма инвестиций €';
            if (commentLabel) commentLabel.innerHTML = 'Комментарий к инвестиции';
            if (contactInput) {
                contactInput.required = true;
                if (contactReqNote) contactReqNote.innerHTML = '<span class="field-req-badge">* (обязательно)</span>';
            }
            if (feedbackCheckbox) {
                feedbackCheckbox.required = true;
                feedbackCheckbox.checked = true;
                if (feedbackReqNote) feedbackReqNote.innerHTML = '<span class="field-req-badge">* (обязательно)</span>';
            }
        }
        renderCustomDropdown();
        // Сбрасываем поле суммы при смене категории
        const amountInputEl = document.getElementById('amountInput');
        if (amountInputEl) amountInputEl.value = '';
        if (wrapper) wrapper.style.opacity = '1';
        isTransitioning = false;
    }, 300);
}

function toggleDropdown() {
    const customDropdown = document.getElementById("customDropdown");
    if (customDropdown) {
        customDropdown.classList.toggle("open");
        const parentGroup = customDropdown.closest(".form-group");
        if (customDropdown.classList.contains("open")) {
            if (parentGroup) parentGroup.style.zIndex = "99999";
        } else {
            if (parentGroup) parentGroup.style.zIndex = "50";
        }
    }
}

function renderCustomDropdown() {
    const menu = document.getElementById("dropdownMenu");
    if (!menu) return;
    menu.innerHTML = "";
    const filtered = optionsData.filter(o => o.category === currentCategory);
    if (filtered.length > 0) {
        selectDropdownItem(filtered[0].title, filtered[0].min_amount_key, filtered[0].project_id || '', filtered[0]);
        filtered.filter(opt => !opt.placeholder).forEach(opt => {
            const item = document.createElement("div");
            item.className = "dropdown-item";
            item.style.padding = "14px 18px";
            item.style.borderRadius = "14px";
            item.style.cursor = "pointer";
            item.style.transition = "var(--transition)";
            const title = document.createElement("div");
            title.style.fontWeight = "700";
            title.textContent = opt.title;
            item.appendChild(title);
            if (opt.min_amount) {
                const minimum = document.createElement("div");
                minimum.style.cssText = "font-size:11px;opacity:.65;margin-top:3px";
                minimum.textContent = `Минимум: ${opt.min_amount} EUR`;
                item.appendChild(minimum);
            }
            item.onmouseenter = () => item.style.background = "var(--accent-bg-glow)";
            item.onmouseleave = () => item.style.background = "transparent";
            item.onclick = () => selectDropdownItem(opt.title, opt.min_amount_key, opt.project_id || '', opt);
            menu.appendChild(item);
        });
    }
}

function updateMinAmountDisplay() {
    const amountInput = document.getElementById("amountInput");
    
    if (amountInput && amountInput.dataset.minKey) {
        const projectMin = parseFloat(amountInput.dataset.projectMin);
        const minVal = projectMin > 0 ? projectMin : (projectLimits[amountInput.dataset.minKey] || 5);
        amountInput.min = minVal;
    }
    fetchExchangeRate();
}

async function fetchExchangeRate() {
    const countryInput = document.getElementById("countryInput");
    const amountInput = document.getElementById("amountInput");
    const hint = document.getElementById("exchangeRateHint");
    if (!countryInput || !amountInput || !hint) return;
    
    const cur = countryInput.dataset.localCurrency || "";
    const amount = parseFloat(amountInput.value);
    if (!cur || cur === "EUR" || !Number.isFinite(amount) || amount <= 0) {
        hint.style.display = "none";
        return;
    }
    
    try {
        hint.style.display = "block";
        hint.innerText = `Расчёт по текущему курсу...`;
        let cached = exchangeRateCache.get(cur);
        if (!cached || Date.now() - cached.savedAt > 5 * 60 * 1000) {
            const res = await fetch(`https://api.frankfurter.dev/v2/rate/EUR/${cur}`);
            if (!res.ok) throw new Error("API error");
            const data = await res.json();
            cached = { rate: Number(data.rate), date: data.date, savedAt: Date.now() };
            exchangeRateCache.set(cur, cached);
        }
        const converted = amount * cached.rate;
        hint.innerText = `По текущему курсу: ${amount.toFixed(2)} EUR ≈ ${converted.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${cur}`;
    } catch (e) {
        console.error("Failed to fetch exchange rate", e);
        hint.innerText = `Не удалось загрузить текущий курс ${cur}`;
    }
}

function selectDropdownItem(title, minKey, projectId = '', option = null) {
    const selectedText = document.getElementById("dropdownSelectedText");
    const optionVal = document.getElementById("optionSelectValue");
    const amountInput = document.getElementById("amountInput");

    if (selectedText) selectedText.innerText = title;
    if (optionVal) {
        optionVal.value = title;
        optionVal.dataset.projectId = projectId;
    }
    if (amountInput) {
        amountInput.dataset.minKey = minKey;
        amountInput.dataset.projectMin = option && option.min_amount ? String(option.min_amount) : '';
    }

    const commentInput = document.getElementById('commentInput');
    if (commentInput) commentInput.placeholder = option && option.custom
        ? 'Опишите детали своего проекта...'
        : 'Укажите детали или пожелания...';
    renderProjectDetails(option);
    
    updateMinAmountDisplay();
    
    const dropdown = document.getElementById("customDropdown");
    if (dropdown) dropdown.classList.remove("open");
    updateSubmitButtonText();
}

function safeProjectUrl(value) {
    try {
        const url = new URL(value);
        return (url.protocol === 'https:' || url.protocol === 'http:') ? url.href : '';
    } catch (_) {
        return '';
    }
}

function renderProjectDetails(option) {
    let details = document.getElementById('projectDetails');
    if (!details) {
        details = document.createElement('div');
        details.id = 'projectDetails';
        details.style.cssText = 'margin-top:10px;font-size:13px;line-height:1.45;opacity:.82';
        document.getElementById('customDropdown')?.insertAdjacentElement('afterend', details);
    }
    details.replaceChildren();
    if (!option || option.placeholder || option.custom) return;
    if (option.description) {
        const description = document.createElement('div');
        description.textContent = option.description;
        details.appendChild(description);
    }
    const safeUrl = safeProjectUrl(option.media_url);
    if (safeUrl) {
        const link = document.createElement('a');
        link.href = safeUrl;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = 'Подробнее о проекте';
        details.appendChild(link);
    }
}

function updateSubmitButtonText() {
    const text = document.getElementById('submitBtnText');
    if (text) text.innerText = 'Отправить заявку';
}

// Country Autocomplete Engine
const countrySearchAliases = {
    RU: ['россия', 'russia'],
    KG: ['киргизия', 'киргизстан'],
    BY: ['белоруссия'],
    GB: ['англия', 'британия'],
    NL: ['голландия'],
    KR: ['южная корея', 'корея'],
    KP: ['северная корея', 'кндр'],
    AE: ['оаэ', 'эмираты'],
    MD: ['молдавия'],
    US: ['америка', 'соединенные штаты']
};

function normalizeCountryQuery(value) {
    return String(value || '')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .replace(/ё/g, 'е')
        .replace(/[^a-zа-я0-9]/g, '');
}

function countryEditDistance(left, right) {
    if (left === right) return 0;
    if (!left.length) return right.length;
    if (!right.length) return left.length;

    let previous = Array.from({ length: right.length + 1 }, (_, i) => i);
    for (let i = 1; i <= left.length; i++) {
        const current = [i];
        for (let j = 1; j <= right.length; j++) {
            current[j] = Math.min(
                current[j - 1] + 1,
                previous[j] + 1,
                previous[j - 1] + (left[i - 1] === right[j - 1] ? 0 : 1)
            );
        }
        previous = current;
    }
    return previous[right.length];
}

function countryMatchScore(country, rawQuery) {
    const query = normalizeCountryQuery(rawQuery);
    const aliases = [
        country.name,
        ...country.keywords,
        ...(countrySearchAliases[country.code] || [])
    ].map(normalizeCountryQuery);
    let best = Number.POSITIVE_INFINITY;

    aliases.forEach(alias => {
        if (!alias) return;
        if (alias === query) best = Math.min(best, 0);
        else if (alias.startsWith(query)) best = Math.min(best, 1);
        else if (alias.includes(query)) best = Math.min(best, 2);
        else if (query.length >= 4) {
            const allowedErrors = query.length >= 7 ? 2 : 1;
            const distance = countryEditDistance(query, alias);
            if (distance <= allowedErrors) best = Math.min(best, 10 + distance);
        }
    });
    return best;
}

function onCountryInput(e) {
    const query = e.target.value.trim().toLowerCase();
    const box = document.getElementById("countrySuggestions");
    if (!box) return;

    delete e.target.dataset.code;
    delete e.target.dataset.localCurrency;
    const hint = document.getElementById("exchangeRateHint");
    if (hint) hint.style.display = "none";

    if (!query) {
        box.style.display = "none";
        box.innerHTML = "";
        return;
    }

    const matches = countryDictionary
        .map(country => ({ country, score: countryMatchScore(country, query) }))
        .filter(result => Number.isFinite(result.score))
        .sort((a, b) => a.score - b.score || a.country.name.localeCompare(b.country.name, 'ru'))
        .map(result => result.country);

    if (matches.length === 0) {
        box.style.display = "none";
        return;
    }

    box.innerHTML = "";
    matches.slice(0, 6).forEach(m => {
        const item = document.createElement("div");
        item.className = "country-suggestion-item";
        const label = document.createElement("span");
        label.textContent = `${m.flag} ${m.name}`;
        item.appendChild(label);
        item.onpointerdown = (e) => {
            e.preventDefault(); // prevent blur
            const input = document.getElementById("countryInput");
            input.value = `${m.flag} ${m.name}`;
            input.dataset.code = m.code;
            input.dataset.localCurrency = countryCurrencyByCode[m.code] || ""; // hint only; payment remains in EUR
            updateMinAmountDisplay();
            box.style.display = "none";
        };
        box.appendChild(item);
    });

    box.style.display = "block";
}

// Contact Autocomplete Suggestions Engine
function showContactSuggestions() {
    const input = document.getElementById("contactInput");
    if (input && !input.value) {
        renderContactBox(contactPresets);
    }
}

function onContactInput(e) {
    const query = e.target.value.trim().toLowerCase();
    if (!query) {
        renderContactBox(contactPresets);
        return;
    }
    const filtered = contactPresets.filter(p => p.type.toLowerCase().includes(query) || p.prefix.toLowerCase().includes(query));
    renderContactBox(filtered.length > 0 ? filtered : contactPresets);
}

function renderContactBox(presets) {
    const box = document.getElementById("contactSuggestions");
    if (!box) return;
    box.innerHTML = "";
    presets.forEach(p => {
        const item = document.createElement("div");
        item.className = "contact-suggestion-item";
        item.innerHTML = `<span style="font-weight:600">${p.type}</span><span style="opacity:0.6; font-size:11px;">${p.placeholder}</span>`;
        item.onpointerdown = (e) => {
            e.preventDefault(); // prevent blur
            const input = document.getElementById("contactInput");
            if (input) {
                let currentVal = input.value.trim();
                currentVal = currentVal.replace(/^(Telegram:\s*@?|WhatsApp:\s*\+?|Email:\s*|Messenger:\s*)/i, '');
                
                if (p.type === "Telegram") {
                    const nick = currentVal.replace(/^@/, '') || '';
                    input.value = nick ? `Telegram: @${nick}` : `Telegram: @`;
                } else if (p.type === "WhatsApp") {
                    const phone = currentVal ? (currentVal.startsWith('+') ? currentVal : '+' + currentVal) : '';
                    input.value = phone ? `WhatsApp: ${phone}` : `WhatsApp: +`;
                } else if (p.type === "Email") {
                    input.value = currentVal ? `Email: ${currentVal}` : `Email: `;
                } else {
                    input.value = currentVal ? `${p.prefix}${currentVal}` : p.prefix;
                }
                input.focus();
            }
            box.style.display = "none";
        };
        box.appendChild(item);
    });
    box.style.display = "block";
}

function toggleFeedbackState() {
    const cb = document.getElementById("feedbackCheckbox");
    if (currentCategory === 'investment' && cb && !cb.checked) {
        cb.checked = true; // Required for investor mode
    }
}

function handleFileSelect(event) {
    const file = event.target.files[0];
    const preview = document.getElementById("filePreview");
    if (file && preview) {
        preview.innerText = file.name.length > 25 ? file.name.substring(0, 22) + '...' : file.name;
        preview.style.opacity = "1";
        preview.style.color = "var(--accent-glow)";
    }
}

function copyTextWithTooltip(event, id) {
    const text = document.getElementById(id).innerText;
    navigator.clipboard.writeText(text).then(() => {
        const tooltip = document.createElement("div");
        tooltip.innerText = "Скопировано!";
        tooltip.style.position = "absolute";
        tooltip.style.background = "#10B981";
        tooltip.style.color = "white";
        tooltip.style.padding = "4px 10px";
        tooltip.style.borderRadius = "8px";
        tooltip.style.fontSize = "12px";
        tooltip.style.fontWeight = "bold";
        tooltip.style.left = event.pageX + 10 + "px";
        tooltip.style.top = event.pageY - 15 + "px";
        tooltip.style.zIndex = "9999";
        tooltip.style.pointerEvents = "none";
        tooltip.style.boxShadow = "0 4px 12px rgba(16,185,129,0.4)";
        tooltip.style.opacity = "0";
        tooltip.style.transition = "opacity 0.2s, transform 0.2s";
        tooltip.style.transform = "translateY(5px)";
        
        document.body.appendChild(tooltip);
        
        requestAnimationFrame(() => {
            tooltip.style.opacity = "1";
            tooltip.style.transform = "translateY(0)";
        });
        
        setTimeout(() => {
            tooltip.style.opacity = "0";
            tooltip.style.transform = "translateY(-5px)";
            setTimeout(() => tooltip.remove(), 200);
        }, 1500);
    });
}

function submitPayment(e) {
    e.preventDefault();
    const btn = document.getElementById("submitBtn");
    
    // Get fields
    const amountInput = document.getElementById("amountInput");
    const amount = amountInput.value;
    const currency = document.getElementById("currencySelect").value;
    const nameInput = document.getElementById("payerNameInput");
    const name = nameInput ? nameInput.value.trim() : "";
    const contact = document.getElementById("contactInput") ? document.getElementById("contactInput").value : "";
    const countryInputEl = document.getElementById("countryInput");
    const country = countryInputEl.value.trim();
    const countryCode = countryInputEl.dataset.code || "";
    const comment = document.getElementById("commentInput").value;
    const feedbackRequested = document.getElementById("feedbackCheckbox") ? document.getElementById("feedbackCheckbox").checked : false;
    const fileInput = document.getElementById("receiptInput");
    const category = document.getElementById("optionSelectValue").value;

    if (currentCategory === 'investment' && !document.getElementById("optionSelectValue").dataset.projectId) {
        alert('Пожалуйста, выберите проект');
        toggleDropdown();
        return;
    }

    // Validation
    const minAmount = parseFloat(amountInput.min) || 5;
    if (!amount || parseFloat(amount) < minAmount) {
        alert(`Пожалуйста, введите сумму не менее ${minAmount}`);
        amountInput.focus();
        return;
    }
    // Страна необязательна - если введена, берём из dataset.code, если нет - пустая строка
    if (country && !countryCode) {
        alert('Выберите страну из списка подсказок или оставьте поле пустым');
        countryInputEl.focus();
        return;
    }


    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = "<span class='material-symbols-rounded' style='vertical-align:middle; margin-right:6px;'>sync</span><span>Отправка заявки...</span>";

    const formData = new FormData();
    formData.append("amount", amount);
    formData.append("currency", currency);
    formData.append("name", name);
    formData.append("contact", contact);
    formData.append("country", country);
    formData.append("country_code", countryCode);
    formData.append("category", `${currentCategory === 'investment' ? 'Инвестор' : 'Донат'}: ${category}`);
    formData.append("comment", comment);
    formData.append("feedback_requested", feedbackRequested ? "true" : "false");
    
    if (currentCategory === 'investment') {
        formData.append("project_id", document.getElementById("optionSelectValue").dataset.projectId);
    }
    if (fileInput && fileInput.files.length > 0) {
        formData.append("receipt", fileInput.files[0]);
    }

    fetch("/api/submit_payment", {
        method: "POST",
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.detail || "Server Error") });
        }
        return response.json();
    })
    .then(data => {
        document.getElementById("paymentForm").style.display = "none";
        const txResultBox = document.getElementById("txResultBox");
        const resultStatusText = document.getElementById("resultStatusText");

        txResultBox.style.display = "block";
        const txCodeContainer = document.getElementById("resTxCode");
        if (txCodeContainer) {
            txCodeContainer.innerText = data.tx_code || "VB-XXXX-XXX";
        }
        
        const dynamicRequisites = document.getElementById("dynamicRequisites");
        if (data.requisites && dynamicRequisites) {
            // Enhanced Copy UI
            let reqHtml = `<div><span style="opacity:0.8;">Перевод по реквизитам:</span></div>`;
            reqHtml += `<div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px; padding:10px; background:rgba(0,0,0,0.2); border-radius:6px; border:1px solid rgba(255,255,255,0.1);">`;
            reqHtml += `<span style="font-family:monospace; font-size:14px; color:#fff;" id="reqTextData">${data.requisites.replace(/\n/g, '<br>')}</span>`;
            reqHtml += `<button type="button" onclick="copyTextWithTooltip(event, 'reqTextData')" style="background:transparent; border:none; color:#10B981; cursor:pointer;" title="Скопировать реквизиты"><span class="material-symbols-rounded">content_copy</span></button>`;
            reqHtml += `</div>`;
            reqHtml += `<div style="margin-top: 15px; font-size: 13px; color: #fbbf24;"><b>ВАЖНО:</b> В назначении платежа обязательно укажите код: <b>${data.tx_code}</b></div>`;

            dynamicRequisites.innerHTML = reqHtml;
            dynamicRequisites.style.display = "block";
            
            const timerContainer = document.getElementById("requisitesTimer");
            if (timerContainer) {
                timerContainer.style.display = "block";
                let durationSeconds = 20 * 60;
                if (data.expires_at) {
                    const expiresAt = new Date(data.expires_at);
                    const now = new Date();
                    durationSeconds = Math.max(0, Math.floor((expiresAt - now) / 1000));
                }
                startCountdown(durationSeconds, document.getElementById("timerCountdown"));
            }
            if (resultStatusText) resultStatusText.innerText = "Заявка зафиксирована. Ожидаем перевод.";
            if (resultStatusText) resultStatusText.innerText = "Заявка зафиксирована. Ожидаем перевод.";
        } else if (resultStatusText) {
            resultStatusText.innerText = currentCategory === 'investment'
                ? 'Заявка инвестора зарегистрирована. Сохраните код заявки — он потребуется для дальнейшей обработки.'
                : 'Заявка успешно зафиксирована.';
        }
    })
    .catch(err => {
        alert("Ошибка при отправке заявки: " + err.message);
        btn.disabled = false;
        btn.innerHTML = originalText;
    });
}

function startCountdown(duration, displayElement) {
    let timer = duration, minutes, seconds;
    const interval = setInterval(function () {
        minutes = parseInt(timer / 60, 10);
        seconds = parseInt(timer % 60, 10);

        minutes = minutes < 10 ? "0" + minutes : minutes;
        seconds = seconds < 10 ? "0" + seconds : seconds;

        if (displayElement) displayElement.textContent = minutes + ":" + seconds;

        if (--timer < 0) {
            clearInterval(interval);
            if (displayElement) displayElement.textContent = "00:00 (Истекло)";
        }
    }, 1000);
}
