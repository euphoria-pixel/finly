import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const p=await PresentationFile.importPptx(await FileBlob.load('/home/euphoria/Загрузки/Telegram Desktop/Презентация проекта.pptx'));
for(const [name,o] of [['shapes',p.slides.items[0].shapes],['shape',p.slides.items[0].shapes.items[0]],['slide',p.slides.items[0]]])console.log(name,Object.getOwnPropertyNames(Object.getPrototypeOf(o)));
