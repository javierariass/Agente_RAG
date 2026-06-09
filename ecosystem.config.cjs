/**
 * PM2 ecosystem: levanta dos procesos en la maquina anfitriona.
 *
 *   agente-rag-api  -> FastAPI/Uvicorn en 0.0.0.0:3090
 *   agente-rag-web  -> Servidor estatico en 0.0.0.0:4000 (rag/web/)
 *
 * Variables de entorno (todas opcionales, ver rag/.env):
 *   API_HOST, API_PORT     bind del API (default 0.0.0.0:3090)
 *   WEB_HOST, WEB_PORT     bind de la web (default 0.0.0.0:4000)
 *   LMSTUDIO_HOST, ...     configuracion del modelo, leida desde rag/.env
 *
 * Arranque:
 *   pm2 start ecosystem.config.cjs
 *   pm2 save
 *   pm2 startup        # genera el comando para activarlo al boot
 */
module.exports = {
  apps: [
    {
      name: "agente-rag-api",
      cwd: "./rag",
      script: "../rag_env/bin/python",
      args: [
        "-m", "uvicorn", "api:app",
        "--host", process.env.API_HOST || "0.0.0.0",
        "--port", process.env.API_PORT || "3090",
        "--workers", "1",
      ].join(" "),
      interpreter: "none",
      autorestart: true,
      max_memory_restart: "2G",
      merge_logs: true,
      time: true,
      out_file: "../logs/rag-api-out.log",
      error_file: "../logs/rag-api-error.log",
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
    {
      name: "agente-rag-web",
      cwd: "./rag/web",
      script: "../../rag_env/bin/python",
      args: [
        "-m", "http.server",
        process.env.WEB_PORT || "4000",
        "--bind", process.env.WEB_HOST || "0.0.0.0",
      ].join(" "),
      interpreter: "none",
      autorestart: true,
      max_memory_restart: "256M",
      merge_logs: true,
      time: true,
      out_file: "../../logs/rag-web-out.log",
      error_file: "../../logs/rag-web-error.log",
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};

