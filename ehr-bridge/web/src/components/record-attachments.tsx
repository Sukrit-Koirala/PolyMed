import {ArrowDownToLine, FileText} from 'lucide-react';
import type {ClinicalFile} from '../lib/clinical-summary';

export function Attachments({files}: {files: ClinicalFile[]}) {
  if (!files?.length) return null;
  return <div className="attachments">{files.map(file =>
    <a key={file.id} href={'/api/files/' + file.id} target="_blank" rel="noopener noreferrer" className="attachment">
      {file.mime.startsWith('image/') ? <img src={'/api/files/' + file.id} alt={file.name}/> : <FileText size={24}/>}
      <span><strong>{file.name}</strong><small>{Math.ceil(file.size / 1024)} KB · {file.mime === 'application/pdf' ? 'Download report' : 'View image'}</small></span>
      <ArrowDownToLine size={14}/>
    </a>
  )}</div>;
}
