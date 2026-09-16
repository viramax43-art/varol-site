global.document = {
    getElementById: function(id) {
        if (id === 'countrySuggestions') {
            return {
                style: {},
                innerHTML: "",
                appendChild: function() {}
            };
        }
        return null;
    },
    createElement: function() { return { style: {} }; },
    querySelectorAll: function() { return []; },
    addEventListener: function() {}
};
global.window = { addEventListener: function(){} };
const fs = require('fs');
eval(fs.readFileSync('static/script.js', 'utf8'));

const e = { target: { value: "Гру" } };
try {
    onCountryInput(e);
    console.log("Success");
} catch(err) {
    console.log("Error:", err);
}
