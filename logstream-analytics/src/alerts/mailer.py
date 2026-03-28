# src/alerts/mailer.py
"""
Módulo de envío de mails para alertas críticas de LogStream Analytics.

Usa SMTP estándar (TLS/STARTTLS). Configuración completa en .env.

"""

import smtplib
import traceback
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, List

from src.core.config import config


class MailerError(Exception):
    """Error al enviar mail de alerta."""
    pass


class Mailer:
    """
    Envía mails de alerta vía SMTP.
    """

    def __init__(self):
        self.host      = config.SMTP_HOST
        self.port      = config.SMTP_PORT
        self.user      = config.SMTP_USER
        self.password  = config.SMTP_PASSWORD
        self.use_tls   = config.SMTP_USE_TLS
        self.mail_from = config.ALERT_MAIL_FROM
        self.mail_to   = config.ALERT_MAIL_TO  # lista

    def is_enabled(self) -> bool:
        """
        Verificar si el envío de mails está habilitado y configurado.

        Returns:
            bool: True si ALERT_EMAIL_ENABLED=true y hay destinatarios.
        """
        if not config.ALERT_EMAIL_ENABLED:
            return False
        if not self.mail_to:
            return False
        if not self.mail_from:
            return False
        return True

    def should_mail_level(self, level: str) -> bool:
        """
        Verificar si el nivel dado debe disparar un mail.

        Args:
            level (str): Nivel del log (INFO, WARNING, ERROR, CRITICAL).

        Returns:
            bool: True si el nivel está en ALERT_MAIL_LEVELS del .env.
        """
        return level in config.ALERT_MAIL_LEVELS

    def _build_message(self, alert: Dict[str, Any]) -> MIMEMultipart:
        """
        Construir el objeto MIMEMultipart del mail de alerta.

        Args:
            alert (dict): Log/alerta con timestamp, source, level, message, etc.

        Returns:
            MIMEMultipart: Mensaje listo para enviar.
        """
        level   = alert.get('level', 'UNKNOWN')
        source  = alert.get('source', 'unknown')
        message = alert.get('message', '')
        ts      = alert.get('timestamp', datetime.now().isoformat())
        ip      = alert.get('client_ip', 'N/A')
        meta    = alert.get('metadata') or {}

        subject = f"[LogStream] {level} en {source} — {ts[:19]}"

        # Cuerpo en texto plano
        body_plain = (
            f"ALERTA DE LOGSTREAM ANALYTICS\n"
            f"{'='*50}\n\n"
            f"Nivel:     {level}\n"
            f"Fuente:    {source}\n"
            f"Timestamp: {ts}\n"
            f"IP cliente:{ip}\n\n"
            f"Mensaje:\n  {message}\n\n"
        )
        if meta:
            body_plain += "Metadata:\n"
            for k, v in meta.items():
                body_plain += f"  {k}: {v}\n"

        body_plain += f"\n{'='*50}\n"
        body_plain += "Este mail fue generado automáticamente por LogStream Analytics.\n"

        # Cuerpo HTML
        meta_rows = "".join(
            f"<tr><td style='padding:4px 8px;color:#666'>{k}</td>"
            f"<td style='padding:4px 8px'>{v}</td></tr>"
            for k, v in meta.items()
        )
        meta_table = (
            f"<table border='1' cellpadding='0' cellspacing='0' "
            f"style='border-collapse:collapse;margin-top:8px'>"
            f"{meta_rows}</table>"
            if meta_rows else "<p>—</p>"
        )

        level_color = {
            'CRITICAL': '#d32f2f',
            'ERROR':    '#f57c00',
            'WARNING':  '#fbc02d',
            'INFO':     '#1976d2',
        }.get(level, '#333')

        body_html = f"""
        <html><body style="font-family:sans-serif;color:#333;max-width:600px">
          <div style="background:{level_color};color:white;padding:16px;border-radius:4px 4px 0 0">
            <h2 style="margin:0">⚠ Alerta LogStream: {level}</h2>
          </div>
          <div style="border:1px solid #ddd;border-top:none;padding:16px;border-radius:0 0 4px 4px">
            <table style="width:100%">
              <tr><td style="color:#666;width:120px">Nivel</td>
                  <td><strong style="color:{level_color}">{level}</strong></td></tr>
              <tr><td style="color:#666">Fuente</td><td>{source}</td></tr>
              <tr><td style="color:#666">Timestamp</td><td>{ts}</td></tr>
              <tr><td style="color:#666">IP cliente</td><td>{ip}</td></tr>
            </table>
            <hr style="margin:16px 0">
            <p><strong>Mensaje:</strong></p>
            <p style="background:#f5f5f5;padding:12px;border-radius:4px;
                       font-family:monospace">{message}</p>
            <p><strong>Metadata:</strong></p>
            {meta_table}
            <hr style="margin:16px 0">
            <p style="color:#999;font-size:12px">
              Mail generado automáticamente por LogStream Analytics.
            </p>
          </div>
        </body></html>
        """

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = self.mail_from
        msg['To']      = ', '.join(self.mail_to)

        msg.attach(MIMEText(body_plain, 'plain', 'utf-8'))
        msg.attach(MIMEText(body_html,  'html',  'utf-8'))

        return msg

    def send_alert(self, alert: Dict[str, Any]) -> bool:
        """
        Enviar mail de alerta para un log dado.

        No lanza excepciones: captura errores y retorna False para
        no interrumpir el loop del Alert Manager.

        Args:
            alert (dict): Log/alerta a notificar.

        Returns:
            bool: True si el mail se envió correctamente.
        """
        if not self.is_enabled():
            return False

        if not self.should_mail_level(alert.get('level', '')):
            return False

        try:
            msg = self._build_message(alert)

            if self.use_tls:
                server = smtplib.SMTP(self.host, self.port, timeout=15)
                server.ehlo()
                server.starttls()
                server.ehlo()
            else:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=15)

            if self.user and self.password:
                server.login(self.user, self.password)

            server.sendmail(
                from_addr=self.mail_from,
                to_addrs=self.mail_to,
                msg=msg.as_string()
            )
            server.quit()

            print(
                f" Mail enviado a {', '.join(self.mail_to)} "
                f"— [{alert.get('level')}] {alert.get('message', '')[:50]}"
            )
            return True

        except smtplib.SMTPAuthenticationError as e:
            print(f" Error de autenticación SMTP: {e}")
            print("   Revisá SMTP_USER y SMTP_PASSWORD en el .env")
        except smtplib.SMTPConnectError as e:
            print(f" No se pudo conectar al servidor SMTP {self.host}:{self.port}: {e}")
        except smtplib.SMTPException as e:
            print(f" Error SMTP al enviar mail: {e}")
        except Exception as e:
            print(f" Error inesperado enviando mail: {e}")
            traceback.print_exc()

        return False

    def send_batch(self, alerts: List[Dict[str, Any]]) -> bool:
        """
        Enviar un mail resumen con múltiples alertas agrupadas.
        Se usa cuando ALERT_MAIL_BATCH_SECONDS > 0.

        Args:
            alerts (List[dict]): Lista de alertas a incluir en el resumen.

        Returns:
            bool: True si el mail se envió correctamente.
        """
        if not alerts or not self.is_enabled():
            return False

        # Filtrar solo los niveles configurados para mail
        alerts_to_send = [
            a for a in alerts
            if self.should_mail_level(a.get('level', ''))
        ]
        if not alerts_to_send:
            return False

        try:
            count   = len(alerts_to_send)
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            subject = f"[LogStream] Resumen de {count} alerta(s) — {now_str}"

            # Texto plano
            body_plain = (
                f"RESUMEN DE ALERTAS — LOGSTREAM ANALYTICS\n"
                f"{'='*50}\n"
                f"Total alertas: {count}\n"
                f"Generado:      {now_str}\n"
                f"{'='*50}\n\n"
            )
            for i, a in enumerate(alerts_to_send, 1):
                body_plain += (
                    f"[{i}] {a.get('level')} | {a.get('source')} | "
                    f"{a.get('timestamp', '')[:19]}\n"
                    f"     {a.get('message', '')}\n\n"
                )

            # HTML — tabla de alertas
            rows_html = ""
            for a in alerts_to_send:
                color = {'CRITICAL': '#d32f2f', 'ERROR': '#f57c00'}.get(
                    a.get('level', ''), '#333'
                )
                rows_html += (
                    f"<tr>"
                    f"<td style='padding:6px 8px'>{a.get('timestamp','')[:19]}</td>"
                    f"<td style='padding:6px 8px;color:{color}'>"
                    f"<strong>{a.get('level')}</strong></td>"
                    f"<td style='padding:6px 8px'>{a.get('source')}</td>"
                    f"<td style='padding:6px 8px'>{a.get('message','')[:80]}</td>"
                    f"</tr>"
                )

            body_html = f"""
            <html><body style="font-family:sans-serif;color:#333;max-width:700px">
              <div style="background:#333;color:white;padding:16px;border-radius:4px 4px 0 0">
                <h2 style="margin:0">📋 Resumen de Alertas LogStream</h2>
                <p style="margin:4px 0 0 0;opacity:0.8">{count} alertas — {now_str}</p>
              </div>
              <div style="border:1px solid #ddd;border-top:none;padding:16px">
                <table style="width:100%;border-collapse:collapse">
                  <thead>
                    <tr style="background:#f5f5f5">
                      <th style="padding:8px;text-align:left">Timestamp</th>
                      <th style="padding:8px;text-align:left">Nivel</th>
                      <th style="padding:8px;text-align:left">Fuente</th>
                      <th style="padding:8px;text-align:left">Mensaje</th>
                    </tr>
                  </thead>
                  <tbody>{rows_html}</tbody>
                </table>
                <hr style="margin:16px 0">
                <p style="color:#999;font-size:12px">
                  Mail generado automáticamente por LogStream Analytics.
                </p>
              </div>
            </body></html>
            """

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From']    = self.mail_from
            msg['To']      = ', '.join(self.mail_to)
            msg.attach(MIMEText(body_plain, 'plain', 'utf-8'))
            msg.attach(MIMEText(body_html,  'html',  'utf-8'))

            if self.use_tls:
                server = smtplib.SMTP(self.host, self.port, timeout=15)
                server.ehlo()
                server.starttls()
                server.ehlo()
            else:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=15)

            if self.user and self.password:
                server.login(self.user, self.password)

            server.sendmail(self.mail_from, self.mail_to, msg.as_string())
            server.quit()

            print(f" Mail resumen enviado ({count} alertas) a {', '.join(self.mail_to)}")
            return True

        except Exception as e:
            print(f" Error enviando mail resumen: {e}")
            traceback.print_exc()
            return False
