'use client';

import type {ReactNode} from 'react';

const safeUrl=(value?:string)=>{try{const url=new URL(value||'');return ['https:','http:'].includes(url.protocol)?url.href:undefined;}catch{return undefined;}};

function InlineMarkdown({text}:{text:string}){
 const tokens=text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g);
 return <>{tokens.map((token,index)=>{
  if(token.startsWith('**')&&token.endsWith('**'))return <strong key={index}>{token.slice(2,-2)}</strong>;
  if(token.startsWith('`')&&token.endsWith('`'))return <code key={index}>{token.slice(1,-1)}</code>;
  const link=token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);const href=safeUrl(link?.[2]);
  if(link)return href?<a key={index} href={href} target="_blank" rel="noreferrer">{link[1]}</a>:<span key={index}>{link[1]}</span>;
  return token;
 })}</>;
}

function MarkdownBlocks({text}:{text:string}){
 const lines=text.replaceAll('\r\n','\n').split('\n');const output:ReactNode[]=[];
 for(let i=0;i<lines.length;){
  const line=lines[i];
  if(!line.trim()){i++;continue;}
  if(line.startsWith('```')){const language=line.slice(3).trim();const code:string[]=[];i++;while(i<lines.length&&!lines[i].startsWith('```'))code.push(lines[i++]);if(i<lines.length)i++;output.push(<pre key={output.length} data-language={language||undefined}><code>{code.join('\n')}</code></pre>);continue;}
  const heading=line.match(/^(#{1,6})\s+(.+)$/);if(heading){const level=Math.min(heading[1].length+2,6);const content=<InlineMarkdown text={heading[2]}/>;output.push(level===3?<h3 key={output.length}>{content}</h3>:level===4?<h4 key={output.length}>{content}</h4>:<h5 key={output.length}>{content}</h5>);i++;continue;}
  if(/^\s*[-*+]\s+/.test(line)){const items:string[]=[];while(i<lines.length&&/^\s*[-*+]\s+/.test(lines[i]))items.push(lines[i++].replace(/^\s*[-*+]\s+/,''));output.push(<ul key={output.length}>{items.map((item,j)=><li key={j}><InlineMarkdown text={item}/></li>)}</ul>);continue;}
  if(/^\s*\d+\.\s+/.test(line)){const items:string[]=[];while(i<lines.length&&/^\s*\d+\.\s+/.test(lines[i]))items.push(lines[i++].replace(/^\s*\d+\.\s+/,''));output.push(<ol key={output.length}>{items.map((item,j)=><li key={j}><InlineMarkdown text={item}/></li>)}</ol>);continue;}
  const paragraph=[line];i++;while(i<lines.length&&lines[i].trim()&&!lines[i].startsWith('```')&&!/^(#{1,6})\s+/.test(lines[i])&&!/^\s*(?:[-*+]|\d+\.)\s+/.test(lines[i]))paragraph.push(lines[i++]);
  output.push(<p key={output.length}>{paragraph.map((part,j)=><span key={j}><InlineMarkdown text={part}/>{j<paragraph.length-1&&<br/>}</span>)}</p>);
 }
 return <>{output}</>;
}

// 当前后端仅保存回答文本，不展示未实现的商品、视频或引用卡片。
export default function AnswerContent({content}:{content:string}){
 return <div className="answer-content rich-answer"><MarkdownBlocks text={content}/></div>;
}
