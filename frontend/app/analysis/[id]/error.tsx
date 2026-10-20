'use client';
export default function ErrorPage({reset}:{reset:()=>void}){return <main className="analysis-page"><h1>Шинжилгээ түр ачаалагдсангүй</h1><p>Архивын холболт эсвэл серверийн ачааллыг дахин шалгаж болно.</p><button className="primary-button" onClick={reset}>Дахин оролдох</button> <a href="/">Нүүр хуудас →</a></main>}
