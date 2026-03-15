import type { Config } from "tailwindcss";

const config: Config = {
    darkMode: "class",
    content: [
        "./pages/**/*.{js,ts,jsx,tsx,mdx}",
        "./components/**/*.{js,ts,jsx,tsx,mdx}",
        "./app/**/*.{js,ts,jsx,tsx,mdx}",
    ],
    theme: {
        extend: {
            colors: {
                primary: "#2e1ded",
                "accent-purple": "#8b5cf6",
                "bg-dark": "#000000",
            },
            fontFamily: {
                display: ["Space Grotesk", "sans-serif"],
            },
        },
    },
    plugins: [],
};
export default config;
