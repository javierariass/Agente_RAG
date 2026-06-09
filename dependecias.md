DESARROLLO 

1- python3 -m venv rag_env
2- source rag_env/bin/activate
3- pip install --upgrade pip
4- pip install fastapi uvicorn openai sentence-transformers faiss-cpu pypdf python-docx python-pptx
5- cd rag
6- ../rag_env/bin/python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload

PRODUCCION

1- sudo apt update
2- sudo apt install -y python3 python3-venv python3-pip curl git nodejs npm
3- sudo npm install -g pm2
4- python3 -m venv rag_env
5- source rag_env/bin/activate
6- pip install --upgrade pip
7- pip install -r requirements.txt
8- pm2 start ecosystem.config.cjs
9- pm2 status
10- pm2 logs agente-rag-api
11- pm2 startup
12- pm2 save

COMANDOS PM2

1- pm2 restart agente-rag-api
2- pm2 stop agente-rag-api
3- pm2 delete agente-rag-api

PRUEBAS RAPIDAS

1- curl http://127.0.0.1:8000/health
2- curl -X POST http://127.0.0.1:8000/query -H "Content-Type: application/json" -d '{"question":"Dime el articulo 38 de derechos inherentes a la personalidad"}'

NOTAS

1- En produccion debe estar activo LM Studio (o endpoint OpenAI compatible) segun la URL de rag/config.py.
2- El primer arranque indexa documentos y puede tardar.
3- Las siguientes ejecuciones usan cache en rag/.cache.