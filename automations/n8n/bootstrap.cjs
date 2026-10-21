/* Run inside the n8n container. Never prints credential JSON. Workflows stay inactive. */
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
if (!process.env.WEBHOOK_KEY || process.env.WEBHOOK_KEY.length < 32) throw new Error('WEBHOOK_KEY debe tener al menos 32 caracteres');
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vigia-import-'));
try {
 const creds = [
  {id:'vigia-header-auth',name:'Vigia webhook key',type:'httpHeaderAuth',data:{name:'X-Webhook-Key',value:process.env.WEBHOOK_KEY}},
  {id:'vigia-smtp',name:'Vigia SMTP',type:'smtp',data:{host:process.env.SMTP_HOST || 'mailpit',port:Number(process.env.SMTP_PORT || 1025),secure:process.env.SMTP_SSL === 'true',disableStartTls:process.env.SMTP_STARTTLS !== 'true',user:process.env.SMTP_USERNAME || '',password:process.env.SMTP_PASSWORD || ''}},
 ];
 const credentialsPath = path.join(dir,'credentials.json');
 fs.writeFileSync(credentialsPath,JSON.stringify(creds),{mode:0o600});
 const run=(args)=>{const result=spawnSync('n8n',args,{stdio:'inherit'});if(result.status!==0)throw new Error('Importación fallida');};
 run(['import:credentials','--input='+credentialsPath]);
 for(const file of fs.readdirSync(__dirname).filter(f=>f.endsWith('.json')).sort()) run(['import:workflow','--input='+path.join(__dirname,file)]);
 process.stdout.write('Credenciales importadas desde entorno. Cuatro flujos importados INACTIVOS; revisar y activar en el editor.\n');
} finally {fs.rmSync(dir,{recursive:true,force:true});}
