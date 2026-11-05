/* Test helper: inspect the same source order served by web_assets.py. */
const fs=require('fs'),path=require('path');
module.exports=function readUISource(entry){
 const root=path.dirname(entry),manifest=JSON.parse(fs.readFileSync(path.join(root,'modules.json'),'utf8'));
 return manifest.scripts.map(name=>fs.readFileSync(path.join(root,name),'utf8')).join('');
};
