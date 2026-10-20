import AdminWorkspace from '../AdminWorkspace';
import Brand from '../Brand';
export const metadata={title:'Удирдлага · OpenWatch',robots:{index:false,follow:false}};
export default function AdminPage(){return <div className="ow-admin-shell"><header><a href="/"><Brand/></a><a className="ow-public-link" href="/">Нийтийн сайт руу ↗</a></header><main><div className="ow-admin-intro"><span>ХАМГААЛАГДСАН УДИРДЛАГА</span><h1>OpenWatch удирдлага</h1><p>Тайлан, эх сурвалж, хандивын мэдээллийг зөвхөн эрхтэй админ удирдана.</p></div><AdminWorkspace/></main></div>}
