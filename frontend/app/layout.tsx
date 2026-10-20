import './globals.css';
import './console.css';
import {LocaleProvider} from './Locale';
export const metadata = {title:'OpenWatch Mongolia — Нээлттэй хяналт',description:'Нээлттэй мэдээлэл. Нотолгоонд суурилсан хяналт.'};
export default function Layout({children}:{children:React.ReactNode}) {return <html lang="mn"><body><LocaleProvider>{children}</LocaleProvider></body></html>}

