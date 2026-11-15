import type {Metadata} from 'next';
import './globals.css';
export const metadata:Metadata={title:'Polymed · Patient-controlled exchange',description:'A focused fictional prototype for hospital records, patient approval, and versioned exchange.'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
