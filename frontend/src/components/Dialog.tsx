'use client';
import {useEffect,useRef,type ReactNode} from 'react';
import {X} from 'lucide-react';
export default function WorkspaceDialog({title,subtitle,onClose,children,wide=false,className='' }:{title:string;subtitle?:string;onClose:()=>void;children:ReactNode;wide?:boolean;className?:string}){
 const box=useRef<HTMLDivElement>(null),close=useRef(onClose);close.current=onClose;
 useEffect(()=>{
  const previous=document.activeElement as HTMLElement;box.current?.focus();
  const handle=(event:KeyboardEvent)=>{
   if(event.key==='Escape')close.current();
   if(event.key==='Tab'){
    const elements=Array.from(box.current?.querySelectorAll<HTMLElement>('button:not([disabled]),a[href],input:not([disabled]),textarea,select,[tabindex="0"]')||[]);
    const first=elements[0],last=elements.at(-1);
    if(!first){event.preventDefault();return;}
    if(event.shiftKey&&(document.activeElement===first||document.activeElement===box.current)){event.preventDefault();last?.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
   }
  };
  const overflow=document.body.style.overflow;document.body.style.overflow='hidden';
  document.addEventListener('keydown',handle);
  return()=>{document.removeEventListener('keydown',handle);document.body.style.overflow=overflow;previous?.focus();};
 },[]);
 return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}><div ref={box} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className={['dialog',wide?'wide-dialog':'',className].filter(Boolean).join(' ')}><div className="dialog-header"><div><h2>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div><button className="icon-button" aria-label="关闭弹窗" onClick={onClose}><X size={20}/></button></div><div className="dialog-body">{children}</div></div></div>;
}
