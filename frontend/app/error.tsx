'use client';
export default function ErrorPage({reset}:{error:Error,reset:()=>void}){
 return <main className="standalone-report"><section className="panel workspace-padding"><h2>Мэдээлэл ачаалж чадсангүй</h2><p className="muted">Серверийн холболт болон үйлчилгээний төлвийг шалгана уу.</p><button className="primary-button" onClick={reset}>Дахин оролдох</button><p><a href="/">Хяналтын самбар руу буцах</a></p></section></main>
}
