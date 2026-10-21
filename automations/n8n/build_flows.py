import json,uuid,pathlib
P=pathlib.Path(__file__).parent
def node(name,typ,params,x,y=0,**extra):
 return dict(id=str(uuid.uuid5(uuid.NAMESPACE_DNS,'vigia.'+name)),name=name,type='n8n-nodes-base.'+typ,typeVersion={'webhook':2,'httpRequest':4.2,'if':2.2,'emailSend':2.1,'scheduleTrigger':1.2}.get(typ,1),position=[x,y],parameters=params,**extra)
def webhook(path):
 return node('Webhook autenticado','webhook',{'httpMethod':'POST','path':path,'authentication':'headerAuth','responseMode':'onReceived','options':{}},0,webhookId=str(uuid.uuid5(uuid.NAMESPACE_DNS,'vigia.webhook.'+path)),credentials={'httpHeaderAuth':{'id':'vigia-header-auth','name':'Vigia webhook key'}})
def http(name,path,x,body=None,method='POST'):
 params={'method':method,'url':"={{ $env.INTERNAL_API_URL + '"+path+"' }}",'sendHeaders':True,'headerParameters':{'parameters':[{'name':'X-Webhook-Key','value':'={{ $env.WEBHOOK_KEY }}'}]},'options':{'timeout':15000}}
 if body is not None:params.update({'sendBody':True,'specifyBody':'json','jsonBody':body})
 return node(name,'httpRequest',params,x,retryOnFail=True,maxTries=2,waitBetweenTries=1000)
def condition(name,expression,x):
 return node(name,'if',{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},'conditions':[{'id':str(uuid.uuid5(uuid.NAMESPACE_DNS, 'vigia.condition.'+name)),'leftValue':expression,'rightValue':True,'operator':{'type':'boolean','operation':'true','singleValue':True}}],'combinator':'and'},'options':{}},x)
def email(x,label='Notificación por correo'):
 return node(label,'emailSend',{'fromEmail':'={{ $env.SMTP_FROM }}','toEmail':'={{ $env.ALERT_RECIPIENT }}','subject':'={{ "Vigía Financiera · " + $("Webhook autenticado").item.json.body.type }}','emailFormat':'text','text':'={{ "Se requiere revisión de indicadores. Evento: " + $("Webhook autenticado").item.json.body.event_id + "\\nAbra la consola: " + $env.APP_URL + "/incidentes\\nNo visite enlaces sospechosos desde el correo." }}','options':{'appendAttribution':False}},x,credentials={'smtp':{'id':'vigia-smtp','name':'Vigia SMTP'}})
def save(file,name,nodes,connections):
 obj={'id':str(uuid.uuid5(uuid.NAMESPACE_DNS, 'vigia.workflow.'+file)),'name':name,'nodes':nodes,'connections':connections,'settings':{'executionOrder':'v1','saveExecutionProgress':False,'saveDataSuccessExecution':'none','saveDataErrorExecution':'all','executionTimeout':60},'active':False,'pinData':{},'tags':[]}
 (P/file).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def conn(target):return {'node':target,'type':'main','index':0}
for file,label,event,path in [('A-alertas.json','A · Alertas de riesgo','risk.alert','vigia-alerts'),('B-escalamiento.json','B · Escalamiento de incidentes','incident.escalate','vigia-escalations')]:
 n=[webhook(path),http('Registrar evento idempotente','/webhooks/events',110,'={{ $json.body }}'),condition('Validar evento',f'={{{{ $json.duplicate === false && $("Webhook autenticado").item.json.body.type === "{event}" }}}}',220),condition('Correo autorizado','={{ $env.EMAIL_NOTIFICATIONS_ENABLED === "true" && $("Webhook autenticado").item.json.body.data.notification_allowed === true }}',440),email(660),http('Registrar entrega','/webhooks/notifications',880,'={{ {event_id: $("Webhook autenticado").item.json.body.event_id, status: "accepted", channel: "email", detail: "Entrega aceptada por SMTP; no confirma lectura."} }}'),http('Registrar omisión','/webhooks/notifications',660,'={{ {event_id: $("Webhook autenticado").item.json.body.event_id, status: "accepted", channel: "email", detail: "Correo desactivado o sin consentimiento."} }}')]
 save(file,label,n,{'Webhook autenticado':{'main':[[conn('Registrar evento idempotente')]]},'Registrar evento idempotente':{'main':[[conn('Validar evento')]]},'Validar evento':{'main':[[conn('Correo autorizado')],[]]},'Correo autorizado':{'main':[[conn('Notificación por correo')],[conn('Registrar omisión')]]},'Notificación por correo':{'main':[[conn('Registrar entrega')]]}})
schedule=node('Programación configurable','scheduleTrigger',{'rule':{'interval':[{'field':'cronExpression','expression':'={{ $env.REPORT_SCHEDULE_CRON || "0 8 * * 1" }}'}]}},0)
summary=http('Resumen autorizado','/automation/summary',220,method='GET')
report=http('Solicitar reporte consolidado','/webhooks/events',440,'={{ {type:"report.request",data:{kind:"consolidated",format:"pdf"},event_id:"scheduled-" + $now.toUTC().toFormat("yyyy-LL-dd-HH-mm")} }}')
save('C-reportes-programados.json','C · Reporte programado',[schedule,summary,report],{'Programación configurable':{'main':[[conn('Resumen autorizado')]]},'Resumen autorizado':{'main':[[conn('Solicitar reporte consolidado')]]}})
n=[webhook('vigia-external'),http('Validar y registrar en API','/webhooks/events',220,'={{ $json.body }}')]
save('D-webhook-externo.json','D · Ingreso externo autenticado',n,{'Webhook autenticado':{'main':[[conn('Validar y registrar en API')]]}})
p=P/'A-alertas.json'
a=json.loads(p.read_text())
a['nodes'].extend([
 condition('Riesgo crítico','={{ $("Webhook autenticado").item.json.body.data.risk === "critical" }}',440),
 node('Activar escalamiento B','httpRequest',{'method':'POST','url':"={{ ($env.N8N_INTERNAL_URL || 'http://n8n:5678') + '/webhook/vigia-escalations' }}",'sendHeaders':True,'headerParameters':{'parameters':[{'name':'X-Webhook-Key','value':'={{ $env.WEBHOOK_KEY }}'}]},'sendBody':True,'specifyBody':'json','jsonBody':'={{ {event_id: $("Webhook autenticado").item.json.body.event_id + "-escalation", type:"incident.escalate", data: $("Webhook autenticado").item.json.body.data} }}','options':{'timeout':15000}},660,retryOnFail=True,maxTries=2,waitBetweenTries=1000)
])
a['nodes'][-2]['position']=[440,300];a['nodes'][-1]['position']=[660,300]
a['connections']['Validar evento']['main'][0].append(conn('Riesgo crítico'))
a['connections']['Riesgo crítico']={'main':[[conn('Activar escalamiento B')],[]]}
p.write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
