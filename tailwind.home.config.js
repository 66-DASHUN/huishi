module.exports = {
  content: ["./templates/home.html", "./static/js/home.js"],
  theme: {
    extend: {
      fontFamily: {
        heading: ["Instrument Serif", "serif"],
        body: ["Barlow", "sans-serif"],
      },
      borderRadius: {
        DEFAULT: "9999px",
      },
    },
  },
};
