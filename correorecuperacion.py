import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def enviar_correo_recuperacion(destinatario, codigo):
    remitente = "huellitas.amor.por.los.animales@gmail.com"
    contraseña = "twhccevzubbcplyp"  # Contraseña de aplicación

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = "Recuperación de contraseña - Huellitas 🐾"
    mensaje["From"] = remitente
    mensaje["To"] = destinatario

    html = f"""
    <html>
      <body style="font-family: Arial; text-align: center; background-color: #f5f5f5; padding: 30px;">
        <div style="background-color: #ffffff; border-radius: 12px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
          <h2 style="color: #4CAF50;">Recuperación de contraseña</h2>
          <p>Hola,</p>
          <p>Has solicitado recuperar tu contraseña de la app <b>Huellitas</b>.</p>
          <p>Tu código de verificación es:</p>
          <h1 style="color: #4CAF50; font-size: 40px; margin: 20px 0;">{codigo}</h1>
          <p style="color: #777; font-size: 14px;">No compartas este código con nadie.</p>
          <p style="color: #777; font-size: 14px;">Este código es válido por 5 minutos.</p>
          <br>
          <p style="font-size: 12px; color: #aaa;">Si no solicitaste este código, ignora este correo.</p>
        </div>
      </body>
    </html>
    """

    mensaje.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(remitente, contraseña)
            server.sendmail(remitente, destinatario, mensaje.as_string())
        print("Correo enviado correctamente")
    except Exception as e:
        print("Error al enviar el correo:", e)
