import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const p=await PresentationFile.importPptx(await FileBlob.load('/home/euphoria/Загрузки/Telegram Desktop/Презентация проекта.pptx'));
await fs.writeFile('.finly-deck/inspection.txt',(await p.inspect({kind:'slide,textbox,shape,image,layout',maxChars:1000000})).ndjson);
for(let i=0;i<p.slides.items.length;i++)await fs.writeFile(`.finly-deck/layout-${i+1}.json`,await (await p.slides.items[i].export({format:'layout'})).text());
console.log('imported',p.slides.items.length);
