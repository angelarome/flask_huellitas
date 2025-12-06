import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def enviar_correo_bienvenida(destinatario, nombre):
    remitente = "huellitas.amor.por.los.animales@gmail.com"
    contraseña = "twhccevzubbcplyp"  # contraseña de aplicación, no la real

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = "¡Bienvenido a Huellitas! 🐾"
    mensaje["From"] = remitente
    mensaje["To"] = destinatario

    html = f"""
    <html>
      <body style="font-family: Arial; text-align: center; background-color: #f5f5f5; padding: 30px;">
        <div style="background-color: #ffffff; border-radius: 12px; padding: 20px;">
          <h2 style="color: #4CAF50;">¡Hola {nombre}! 💚</h2>
          <p>Gracias por registrarte en <b>Huellitas</b>.</p>
          <p>Estamos felices de tenerte aquí 🐶🐱</p>
          <br>
          <p style="font-size: 14px; color: #777;">Equipo Huellitas</p>
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
