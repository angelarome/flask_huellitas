import base64
from urllib import response
from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
import os
from werkzeug.utils import secure_filename
from datetime import timedelta, time, date
from correo import enviar_correo_bienvenida
from datetime import datetime, timedelta, date
from flask import request, jsonify
import bcrypt
import requests
from correorecuperacion import enviar_correo_recuperacion
import random
from decimal import Decimal

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
def get_connection():
    try:
        db = mysql.connector.connect(
            host=os.environ.get("DB_HOST"),
            port=int(os.environ.get("DB_PORT", 10512)),
            user=os.environ.get("DB_USER"),
            password=os.environ.get("DB_PASS"),
            database=os.environ.get("DB_NAME")
        )
        return db
    except Error as e:
        print(f"Error conectando a MySQL: {e}")
        return None


# 🔥 Nuevo endpoint para Ollama
@app.route("/chat", methods=["POST"])
def chat_with_ollama():
    try:
        data = request.get_json()
        mensaje = data.get("mensaje", "")
        
        if not mensaje:
            return jsonify({"error": "No se proporcionó mensaje"}), 400

        # Configuración para Ollama local
        ollama_url = "http://localhost:11434/api/generate"
        payload = {
            "model": "phi3:mini",
            "prompt": f"""
            Eres FirulAI, un asistente especializado en mascotas. 
            Responde de manera CONCISA y directa (máximo 100 palabras).
            Sé amable pero ve al grano.
            
            Pregunta: {mensaje}
            
            Respuesta concisa:
            """,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 150  # Limita la longitud de respuesta
            }
        }

        response = requests.post(ollama_url, json=payload, timeout=45) # segundos
        
        if response.status_code == 200:
            result = response.json()
            respuesta = result.get("response", "Lo siento, no pude generar una respuesta.")
            return jsonify({"respuesta": respuesta})
        else:
            return jsonify({"error": "Error al conectar con Ollama"}), 500

    except Exception as e:
        print(f"Error en chat: {e}")
        return jsonify({"error": str(e)}), 500
    
    
# ✅ Obtener lista de usuarios
@app.route("/usuarios", methods=["GET"])
def obtener_usuarios():
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM `dueno_mascotas`;")
    resultados = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify(resultados)


@app.route("/registrar", methods=["POST"])
def registrar_usuario():
    data = request.get_json()
    cedula = data.get("cedula")
    nombre = data.get("nombre")
    apellido = data.get("apellido")
    telefono = data.get("telefono")
    correo = data.get("correo")
    direccion = data.get("direccion")
    contrasena = data.get("contrasena")
    imagen_base64 = data.get("imagen")
    departamento = data.get("departamento")
    ciudad = data.get("ciudad")

    contrasena_cifrada = bcrypt.hashpw(contrasena.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    if not all([cedula, nombre, apellido, telefono, correo, direccion, contrasena, departamento, ciudad]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400
    
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    
    # 🔎 Verificar si ya existe
    sql_verificar = """
        SELECT * FROM usuarios 
        WHERE correo = %s 
    """
    cursor.execute(sql_verificar, (correo,))
    existente = cursor.fetchone()

    if existente:
        cursor.close()
        db.close()
        return jsonify({"error": "El usuario ya está registrado"}), 409
    
    # 1️⃣ Insertar en usuarios primero
    sql_usuario = """
        INSERT INTO usuarios (correo, contrasena, rol)
        VALUES (%s, %s, %s)
    """
    valores_usuario = (correo, contrasena_cifrada, 'dueno')
    cursor.execute(sql_usuario, valores_usuario)
    db.commit()

    # 2️⃣ Obtener el ID del usuario recién creado
    id_usuario = cursor.lastrowid

    # 3️⃣ Insertar en dueno_mascotas
    sql_dueno = """
        INSERT INTO dueno_mascotas (id_dueno, cedula, nombre, apellido, telefono, correo, departamento, ciudad, direccion, contraseña, foto_perfil)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    valores_dueno = (id_usuario, cedula, nombre, apellido, telefono, correo, departamento, ciudad, direccion, contrasena_cifrada, imagen_base64)
    cursor.execute(sql_dueno, valores_dueno)
    db.commit()
    
    try:
        enviar_correo_bienvenida(correo, nombre)
    except Exception as e:
        print("Error enviando correo:", e)

    # 🔹 Recuperar los datos recién insertados
    cursor.execute("SELECT id_dueno, cedula, nombre, apellido, telefono, departamento, ciudad, direccion, foto_perfil FROM dueno_mascotas WHERE id_dueno = %s", 
                   (id_usuario,))
    usuario = cursor.fetchone()
    
    cursor.close()
    db.close()
    
    return jsonify({
        "mensaje": "Usuario registrado correctamente",
        "usuario": usuario
    }), 201


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    correo = data.get("correo")
    contrasena = data.get("contrasena")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    sql = "SELECT * FROM usuarios WHERE correo = %s"
    cursor.execute(sql, (correo,))
    usuario = cursor.fetchone()

    if not usuario:
        cursor.close()
        db.close()
        return jsonify({"error": "Correo no encontrado"}), 404

    # 2️⃣ Verificar contraseña con bcrypt
    contrasena_cifrada = usuario["contrasena"].encode("utf-8")
    if not bcrypt.checkpw(contrasena.encode("utf-8"), contrasena_cifrada):
        cursor.close()
        db.close()
        return jsonify({"error": "Contraseña incorrecta"}), 401

    # 3️⃣ Si es correcta, verificar el rol y traer datos relacionados
    rol = usuario["rol"]
    id_usuario = usuario["id_usuario"]

    if rol == "dueno":
        sql_detalle = """
            SELECT id_dueno, cedula, nombre, apellido, telefono, correo, departamento, ciudad, direccion, foto_perfil 
            FROM dueno_mascotas
            WHERE id_dueno = %s
        """
    elif rol == "veterinaria":
        sql_detalle = """
            SELECT id_veterinaria 
            FROM veterinaria
            WHERE id_veterinaria = %s
        """
        
    elif rol == "tienda":
        sql_detalle = """
            SELECT idtienda 
            FROM tienda
            WHERE idtienda = %s
        """
    elif rol == "paseador":
        sql_detalle = """
            SELECT id_paseador
            FROM paseador
            WHERE id_paseador = %s
        """
    else:
        cursor.close()
        db.close()
        return jsonify({"error": "Rol no reconocido"}), 400

    cursor.execute(sql_detalle, (id_usuario,))
    datos_relacionados = cursor.fetchone()

    cursor.close()
    db.close()

    return jsonify({
        "mensaje": "Inicio de sesión exitoso",
        "usuario": usuario,
        "detalles": datos_relacionados
    }), 200


@app.route("/recuperarcontrasena", methods=["POST"])
def recuperarContrasena():
    data = request.get_json()
    correo = data.get("correo")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # 1️⃣ Verificar que el correo exista
    sql = "SELECT * FROM usuarios WHERE correo = %s"
    cursor.execute(sql, (correo,))
    usuario = cursor.fetchone()

    if not usuario:
        cursor.close()
        db.close()
        return jsonify({"error": "Correo no encontrado"}), 404

    # 2️⃣ Generar código y expiración
    codigo = str(random.randint(100000, 999999))
    expira = datetime.now() + timedelta(minutes=5)

    # 3️⃣ Borrar códigos anteriores del mismo correo
    cursor.execute("DELETE FROM codigos_recuperacion WHERE correo = %s", (correo,))

    # 4️⃣ Insertar el nuevo código
    sql = """
        INSERT INTO codigos_recuperacion (correo, codigo, expiracion)
        VALUES (%s, %s, %s)
    """
    cursor.execute(sql, (correo, codigo, expira))
    db.commit()

    # 5️⃣ Enviar correo con el código
    enviar_correo_recuperacion(correo, codigo)

    cursor.close()
    db.close()

    # 6️⃣ Respuesta para Flutter
    return jsonify({
        "usuario": usuario
    }), 200
    
@app.route("/codigo", methods=["POST"])
def ObtenerCodigo():
    data = request.get_json()
    correo = data.get("correo")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    sql = "SELECT codigo, expiracion FROM codigos_recuperacion WHERE correo = %s"
    cursor.execute(sql, (correo,))
    codigo = cursor.fetchone()

    cursor.close()
    db.close()

    if not codigo:
        return jsonify({"error": "Codigo no encontrado"}), 404
    
    # Convertir expiración a string ISO-8601 que Flutter SÍ entiende
    expiracion = codigo["expiracion"]

    if isinstance(expiracion, (datetime, date)):
        codigo["expiracion"] = expiracion.isoformat()
    else:
        codigo["expiracion"] = str(expiracion).replace(" ", "T")
        
    return jsonify(codigo)

@app.route("/cambiarcontrasena", methods=["PUT"])
def cambiarcontrasena():
    data = request.get_json()
    correo = data.get("correo")
    contrasena = data.get("contrasena")
    rol = data.get("rol")
    print("correo:", correo, "rol:", rol, "contrasena:", contrasena)
    
    contrasena_cifrada = bcrypt.hashpw(contrasena.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    if not all([correo, contrasena]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400
    
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    
    # Actualizar contraseña en usuarios
    sql = "UPDATE usuarios SET contrasena = %s WHERE correo = %s"
    cursor.execute(sql, (contrasena_cifrada, correo,))
    db.commit()
    
    # Actualizar contraseña en la tabla correspondiente según rol
    if rol == "dueno":
        sql_detalle = "UPDATE dueno_mascotas SET contraseña = %s WHERE correo = %s"
    elif rol == "veterinaria":
        sql_detalle = "UPDATE veterinaria SET contrasena = %s WHERE correo = %s"
    elif rol == "tienda":
        sql_detalle = "UPDATE tienda SET contrasena = %s WHERE correo = %s"
    elif rol == "paseador":
        sql_detalle = "UPDATE paseador SET contrasena = %s WHERE correo = %s"
    else:
        cursor.close()
        db.close()
        return jsonify({"error": "Rol no reconocido"}), 400

    cursor.execute(sql_detalle, (contrasena_cifrada, correo,))
    db.commit()  # 🔹 commit necesario
    # datos_relacionados = cursor.fetchone()  <-- innecesario

    cursor.close()
    db.close()
        
    return jsonify({"mensaje": "Contraseña cambiada correctamente"}), 200
    
@app.route("/actualizar_imagen", methods=["PUT"])
def actualizar_imagen():
    data = request.get_json()
    id = data.get("id")
    foto_perfil = data.get("foto_perfil")

    if not id or not foto_perfil:
        return jsonify({"error": "Faltan datos"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE dueno_mascotas SET foto_perfil = %s WHERE id_dueno = %s"
    cursor.execute(sql, (foto_perfil, id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Imagen actualizada correctamente"}), 200


@app.route("/actualizar_imagen_mascota", methods=["PUT"])
def actualizar_imagen_mascota():
    data = request.get_json()
    id_mascota = data.get("idMascota")
    foto_perfil = data.get("fotoMascota")

    if not id_mascota or not foto_perfil:
        return jsonify({"error": "Faltan datos"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE mascotas SET imagen_perfil = %s WHERE id_mascotas = %s"
    cursor.execute(sql, (foto_perfil, id_mascota))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Imagen actualizada correctamente"}), 200

    
@app.route("/registrarMascota", methods=["POST"])
def registrar_mascota():
    data = request.get_json()

    nombre = data.get("nombre")
    apellido = data.get("apellido")
    raza = data.get("raza")
    genero = data.get("genero")
    peso = data.get("peso")
    especies = data.get("especie")
    fecha_nacimiento = data.get("fecha_nacimiento")
    imagen_base64 = data.get("imagen")
    esterilizado = data.get("esterilizado")
    id_dueno = data.get("id_dueno")

    if not all([nombre, apellido, raza, genero, peso, especies, fecha_nacimiento, imagen_base64, id_dueno, esterilizado]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400
    
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # Insertar mascota
    sql = """
        INSERT INTO mascotas (nombre, apellido, raza, peso, fecha_nacimiento, sexo, especies, esterilizado, imagen_perfil)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    valores = (nombre, apellido, raza, peso, fecha_nacimiento, genero, especies, esterilizado, imagen_base64)
    cursor.execute(sql, valores)
    db.commit()

    id_mascota = cursor.lastrowid

    # Consultar la fila recién insertada
    cursor.execute("SELECT nombre, especies, sexo, fecha_nacimiento FROM mascotas WHERE id_mascotas = %s", (id_mascota,))
    mascota = cursor.fetchone()

    # Insertar relación usuario_mascota
    cursor.execute(
        "INSERT INTO duenosymascotas (id_mascota, id_dueno) VALUES (%s, %s)",
        (id_mascota, id_dueno)
    )
    db.commit()

    cursor.close()
    db.close()

    resultado = {
        "id_mascotas": id_mascota,
        "nombre": mascota["nombre"],
        "especies": mascota["especies"],
        "sexo": mascota["sexo"],
        "fecha_nacimiento": mascota["fecha_nacimiento"].strftime("%Y-%m-%d") if mascota["fecha_nacimiento"] else None
    }

    return jsonify({"mensaje": "Mascota registrada correctamente", "mascota": resultado}), 201

@app.route("/editarMascota", methods=["PUT"])
def editar_mascota():
    data = request.get_json()
    id_mascota = data.get("id_mascota")
    nombre = data.get("nombre")
    apellido = data.get("apellido")
    raza = data.get("raza")
    genero = data.get("genero")
    peso = data.get("peso")
    especies = data.get("especie")
    fecha_nacimiento = data.get("fecha_nacimiento")
    imagen_base64 = data.get("imagen")
    esterilizado = data.get("esterilizado")

    if not all([nombre, apellido, raza, genero, peso, especies, fecha_nacimiento, imagen_base64, esterilizado]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400
    
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # Insertar mascota
    sql = """
        UPDATE mascotas SET nombre = %s, apellido = %s, raza = %s, peso = %s, fecha_nacimiento = %s, sexo = %s, especies = %s, esterilizado = %s, imagen_perfil = %s WHERE id_mascotas = %s
    """
    valores = (nombre, apellido, raza, peso, fecha_nacimiento, genero, especies, esterilizado, imagen_base64, id_mascota)
    cursor.execute(sql, valores)
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Mascota editada correctamente"}), 201

@app.route("/mascotas", methods=["POST"])
def mascotas():
    data = request.get_json()
    id_dueno = data.get("id_dueno")

    if not id_dueno:
        return jsonify({"error": "Falta el id"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    sql = """
        SELECT m.id_mascotas, m.nombre, m.especies, m.sexo, m.fecha_nacimiento, m.imagen_perfil
        FROM mascotas m
        JOIN duenosymascotas um ON m.id_mascotas = um.id_mascota
        WHERE um.id_dueno = %s
    """
    cursor.execute(sql, (id_dueno,))
    mascotas = cursor.fetchall()
    cursor.close()
    db.close()

    for m in mascotas:
        
        if m["fecha_nacimiento"]:
            m["fecha_nacimiento"] = m["fecha_nacimiento"].strftime("%Y-%m-%d")
        imagen = m.get("imagen_perfil")
        if imagen:
            if isinstance(imagen, (bytes, bytearray)):
                m["imagen_perfil"] = base64.b64encode(imagen).decode("utf-8")
            # Si ya es texto (por ejemplo, un path o un base64), lo dejamos igual
            elif isinstance(imagen, str):
                m["imagen_perfil"] = imagen

    return jsonify({"mascotas": mascotas}), 200

@app.route("/higiene", methods=["POST"])
def higiene():
    data = request.get_json()
    id_mascota = data.get("id_mascota")

    if not id_mascota:
        return jsonify({"error": "Falta el ID de la mascota"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    sql = """
        SELECT h.id_higiene, h.frecuencia, h.dias_personalizados, h.notas, h.tipo, h.hora, h.fecha
        FROM higiene h
        WHERE h.id_mascota = %s
    """
    cursor.execute(sql, (id_mascota,))
    higiene = cursor.fetchall()
    cursor.close()
    db.close()
    for h in higiene:
        if isinstance(h.get("hora"), timedelta):
            total_seconds = int(h["hora"].total_seconds())
            horas = total_seconds // 3600
            minutos = (total_seconds % 3600) // 60
            h["hora"] = f"{horas:02d}:{minutos:02d}"
        elif isinstance(h.get("hora"), time):
            h["hora"] = h["hora"].strftime("%H:%M")
        
        if isinstance(h.get("fecha"), date):
            h["fecha"] = h["fecha"].strftime("%Y-%m-%d")

    return jsonify({"higiene": higiene}), 200

@app.route("/medicamento", methods=["POST"])
def medicamento():
    data = request.get_json()
    id_mascota = data.get("id_mascota")

    if not id_mascota:
        return jsonify({"error": "Falta el ID de la mascota"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    sql = """
        SELECT id_medicamento, tipo, dosis, unidad, frecuencia, dias_personalizados, hora, fecha, descripcion
        FROM medicamento 
        WHERE id_mascota = %s
    """
    cursor.execute(sql, (id_mascota,))
    medicamento = cursor.fetchall()
    cursor.close()
    db.close()
    for h in medicamento:
        if isinstance(h.get("hora"), timedelta):
            total_seconds = int(h["hora"].total_seconds())
            horas = total_seconds // 3600
            minutos = (total_seconds % 3600) // 60
            h["hora"] = f"{horas:02d}:{minutos:02d}"
        elif isinstance(h.get("hora"), time):
            h["hora"] = h["hora"].strftime("%H:%M")
        
        if isinstance(h.get("fecha"), date):
            h["fecha"] = h["fecha"].strftime("%Y-%m-%d")

    return jsonify({"medicamento": medicamento}), 200
    
@app.route("/registrarHigiene", methods=["POST"])
def registrar_higiene():
    data = request.get_json()

    frecuencia = data.get("frecuencia")
    dias_personalizados = data.get("dias_personalizados")
    notas = data.get("notas")
    tipo = data.get("tipo")
    fecha = data.get("fecha")
    hora = data.get("hora")
    id_mascota = data.get("id_mascota")

    if not all([frecuencia, tipo, fecha, hora, id_mascota]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # Insertar higiene
    sql = """
        INSERT INTO higiene (id_mascota, frecuencia, dias_personalizados, notas, tipo, fecha, hora)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    valores = (id_mascota, frecuencia, dias_personalizados, notas, tipo, fecha, hora)
    cursor.execute(sql, valores)
    db.commit()

    id_bano = cursor.lastrowid
    
    cursor.close()
    db.close()
    return jsonify({
        "mensaje": "Higiene registrada correctamente",
        "higiene": {
            "id_bano": id_bano,
            "id_mascota": id_mascota,
            "frecuencia": frecuencia,
            "notas": notas,
            "tipo": tipo,
            "fecha": fecha,
            "hora": hora
        }
    }), 201
    
@app.route("/registrarMedicamento", methods=["POST"])
def registrar_medicamento():
    data = request.get_json()
    id_mascota = data.get("id_mascota")
    frecuencia = data.get("frecuencia")
    dosis = data.get("dosis")
    unidad = data.get("unidad")
    notas = data.get("notas")
    tipo = data.get("tipo")
    dias_personalizados = data.get("dias_personalizados")
    fecha = data.get("fecha")
    hora = data.get("hora")

    if not all([tipo, fecha, hora, id_mascota, dosis, unidad]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # Insertar higiene
    sql = """
        INSERT INTO medicamento (id_mascota, tipo, dosis, unidad, frecuencia, dias_personalizados, hora, fecha, descripcion)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    valores = (id_mascota, tipo, dosis, unidad, frecuencia, dias_personalizados, hora, fecha, notas)
    cursor.execute(sql, valores)
    db.commit()
    
    cursor.close()
    db.close()
    return jsonify({
        "mensaje": "Medicamento registrado correctamente",
    }), 201
    
@app.route("/editarMedicamento", methods=["PUT"])
def editar_medicamento():
    data = request.get_json()
    id_mascota = data.get("id_mascota")
    id_medicamento = data.get("id_medicamento")
    frecuencia = data.get("frecuencia")
    dosis = data.get("dosis")
    unidad = data.get("unidad")
    notas = data.get("notas")
    tipo = data.get("tipo")
    dias_personalizados = data.get("dias_personalizados")
    fecha = data.get("fecha")
    hora = data.get("hora")

    if not all([tipo, fecha, hora, id_mascota, dosis, unidad]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # Insertar higiene
    sql = """
            UPDATE medicamento
            SET tipo = %s,
                dosis = %s,
                unidad = %s,
                frecuencia = %s,
                dias_personalizados = %s,
                hora = %s,
                fecha = %s,
                descripcion = %s
            WHERE id_medicamento = %s
        """

    valores = (tipo, dosis, unidad, frecuencia, dias_personalizados, hora, fecha,notas, id_medicamento)
    cursor.execute(sql, valores)
    db.commit()
    
    cursor.close()
    db.close()
    return jsonify({
        "mensaje": "Medicamento editado correctamente",
    }), 201

@app.route("/obtenermascota", methods=["POST"])
def obtener_mascotas():
    data = request.get_json()
    id_mascota = data.get("id_mascota")
    
    if not id_mascota:
        return jsonify({"error": "Falta el ID de la mascota"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM `mascotas` WHERE id_mascotas = %s;", (id_mascota,))
    resultados = cursor.fetchall()
    cursor.close()
    db.close()
    
    for m in resultados:
        if m["fecha_nacimiento"]:
            m["fecha_nacimiento"] = m["fecha_nacimiento"].strftime("%Y-%m-%d")
        imagen = m.get("imagen_perfil")
        if imagen:
            if isinstance(imagen, (bytes, bytearray)):
                m["imagen_perfil"] = base64.b64encode(imagen).decode("utf-8")
            # Si ya es texto (por ejemplo, un path o un base64), lo dejamos igual
            elif isinstance(imagen, str):
                m["imagen_perfil"] = imagen
    
    return jsonify({"mascotas": resultados})

@app.route('/eliminar_medicamento', methods=['DELETE'])
def eliminar_medicamento():
    data = request.get_json()
    id_mascota = data.get("id_mascota")
    id_medicamento = data.get("id_medicamento")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500
    # Aquí haces la lógica para eliminar el registro de higiene
    cursor = db.cursor(dictionary=True)
    cursor.execute("DELETE FROM medicamento WHERE id_mascota = %s AND id_medicamento = %s", (id_mascota, id_medicamento))
    db.commit()

    return jsonify({"mensaje": "Medicamento eliminado correctamente"}), 200

@app.route('/eliminar_higiene', methods=['DELETE'])
def eliminar_higiene():
    data = request.get_json()
    id_mascota = data.get("id_mascota")
    id_higiene = data.get("id_higiene")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500
    # Aquí haces la lógica para eliminar el registro de higiene
    cursor = db.cursor(dictionary=True)
    cursor.execute("DELETE FROM higiene WHERE id_mascota = %s AND id_higiene = %s", (id_mascota, id_higiene))
    db.commit()

    return jsonify({"mensaje": "Higiene eliminada correctamente"}), 200

@app.route("/actualizar_higiene", methods=["PUT"])
def actualizar_higiene():
    data = request.get_json()
    id_higiene = data.get("id_higiene")
    frecuencia = data.get("frecuencia")
    dias_personalizados = data.get("dias_personalizados")
    notas = data.get("notas")
    tipo = data.get("tipo")
    fecha = data.get("fecha")
    hora = data.get("hora")

    def vacio(x): return x is None or str(x).strip() == ""
    if any(vacio(c) for c in [frecuencia, tipo, fecha, hora]):
        return jsonify({"error": "Faltan datos"}), 400


    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE higiene SET frecuencia = %s, dias_personalizados = %s, notas = %s, tipo = %s, fecha = %s, hora = %s WHERE id_higiene = %s"
    cursor.execute(sql, (frecuencia, dias_personalizados, notas, tipo, fecha, hora, id_higiene))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Higiene actualizada correctamente"}), 200

@app.route("/mitienda", methods=["POST"])
def obtenerMiTienda():
    data = request.get_json()
    id = data.get("id")

    if not id:
        return jsonify({"error": "Falta la cédula"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM `tienda` WHERE idtienda = %s;", (id,))
    resultados = cursor.fetchall()
    cursor.close()
    db.close()
    
    def convertir_tiempo(valor):
        """Convierte timedelta o time a 'HH:MM'"""
        if isinstance(valor, timedelta):
            total_seconds = int(valor.total_seconds())
            horas = total_seconds // 3600
            minutos = (total_seconds % 3600) // 60
            return f"{horas:02d}:{minutos:02d}"
        elif isinstance(valor, time):
            return valor.strftime("%H:%M")
        return valor  # si ya es string o None

    # 🔁 Convertir todos los campos de tipo timedelta/time
    for tienda in resultados:
        for k, v in tienda.items():
            tienda[k] = convertir_tiempo(v)

    return jsonify({"tienda": resultados})

@app.route('/eliminarMascota', methods=['DELETE'])
def eliminarMascota():
    data = request.get_json()
    id_mascota = data.get("id_mascota")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500
    # Aquí haces la lógica para eliminar el registro de higiene
    cursor = db.cursor(dictionary=True)
    cursor.execute("DELETE FROM mascotas WHERE id_mascotas = %s", (id_mascota,))
    db.commit()

    return jsonify({"mensaje": "Mascota eliminada correctamente"}), 200


@app.route("/registrarTienda", methods=["POST"])
def registrarTienda():
    data = request.get_json()
    cedulaUsuario = data.get("cedulaUsuario")
    imagen = data.get("imagen")
    nombre_negocio = data.get("nombre_negocio")
    descripcion = data.get("descripcion")
    direccion = data.get("direccion")
    telefono = data.get("telefono")
    domicilio = data.get("domicilio")
    horariolunesviernes = data.get("horariolunesviernes")
    cierrelunesviernes = data.get("cierrelunesviernes")
    horariosabado = data.get("horariosabado")
    cierrehorasabado = data.get("cierrehorasabado")
    horariodomingos = data.get("horariodomingos")
    cierredomingos = data.get("cierredomingos")
    metodopago = data.get("metodopago")
    correo = data.get("correo")
    contrasena = data.get("contrasena")
    departamento = data.get("departamento")
    ciudad = data.get("ciudad")
    
    contrasena_cifrada = bcrypt.hashpw(contrasena.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    if not all([cedulaUsuario, imagen, nombre_negocio, direccion, telefono, domicilio, horariolunesviernes, cierrelunesviernes, horariosabado, cierrehorasabado, metodopago, correo, contrasena, departamento, ciudad]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    
    cursor = db.cursor(dictionary=True)

    sql_verificar = """
        SELECT * FROM usuarios 
        WHERE correo = %s 
    """
    cursor.execute(sql_verificar, (correo,))
    existente = cursor.fetchone()

    if existente:
        cursor.close()
        db.close()
        return jsonify({"error": "El usuario ya está registrado"}), 409
    
    # 1️⃣ Insertar en usuarios primero
    sql_usuario = """
        INSERT INTO usuarios (correo, contrasena, rol)
        VALUES (%s, %s, %s)
    """
    valores_usuario = (correo, contrasena_cifrada, 'tienda')
    cursor.execute(sql_usuario, valores_usuario)
    db.commit()

    id_usuario = cursor.lastrowid

    # 3️⃣ Insertar en dueno_mascotas
    sql = """
        INSERT INTO tienda (idtienda, imagen, cedula_usuario, nombre_negocio, descripcion, departamento, ciudad, direccion, telefono, domicilio, horariolunesviernes, cierrelunesviernes, horariosabado, cierresabado, horariodomingo, cierredomingo, metodo_pago, correo, contrasena)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    valores = (id_usuario, imagen, cedulaUsuario, nombre_negocio, descripcion, departamento, ciudad, direccion, telefono, domicilio, horariolunesviernes, cierrelunesviernes, horariosabado, cierrehorasabado, horariodomingos, cierredomingos, metodopago, correo, contrasena_cifrada)
    cursor.execute(sql, valores)
    db.commit()

    id_tienda = cursor.lastrowid
    
    cursor.close()
    db.close()
    return jsonify({
        "mensaje": "Tienda registrada correctamente",
        "mitienda": {
            "idtienda": id_tienda,
            "imagen": imagen, 
            "cedulaUsuario": cedulaUsuario,
            "nombre_negocio": nombre_negocio,
            "descripcion": descripcion,
            "departamento": departamento,
            "ciudad": ciudad,
            "telefono": telefono,
            "domicilio": domicilio,
            "horariolunesviernes": horariolunesviernes,
            "cierrelunesviernes": cierrelunesviernes,
            "horariosabado": horariosabado,
            "cierresabado": cierrehorasabado,
            "horariodomingos": horariodomingos,
            "cierredomingos": cierredomingos,
            "metodopago": metodopago
        
        }
    }), 201
    
@app.route("/actualizar_imagen_tienda", methods=["PUT"])
def actualizar_imagen_tienda():
    data = request.get_json()
    id = data.get("id")
    imagen = data.get("imagen")

    if not id or not imagen:
        return jsonify({"error": "Faltan datos"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE tienda SET imagen = %s WHERE idtienda = %s"
    cursor.execute(sql, (imagen, id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Imagen actualizada correctamente"}), 200

@app.route("/comentariosTienda", methods=["POST"])
def obtener_comentariosTienda():
    data = request.get_json()
    print("DATA RECIBIDA:", data)
    id_tienda = data.get("id_tienda")

    if not id_tienda:
        return jsonify({"error": "Falta el id tienda"}), 400
    
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    sql = """
        SELECT c.*, u.nombre, u.apellido, u.foto_perfil
        FROM calificacion c
        JOIN dueno_mascotas u ON c.id_dueno = u.id_dueno
        WHERE c.id_tienda = %s
    """
    cursor.execute(sql, (id_tienda,))
    calificacion = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify({"calificacion": calificacion}), 200


@app.route("/promedioTienda", methods=["POST"])
def promedio_tienda():
    datos = request.get_json()
    id_tienda = datos.get("id_tienda")

    db = get_connection()
    cursor = db.cursor(dictionary=True)

    # Obtenemos todas las calificaciones y el promedio
    sql = "SELECT calificacion FROM calificacion WHERE id_tienda = %s"
    cursor.execute(sql, (id_tienda,))
    calificaciones = cursor.fetchall()

    if not calificaciones:
        promedio = 0
    else:
        suma = sum([c["calificacion"] for c in calificaciones])
        promedio = round(suma / len(calificaciones), 1)  # promedio con 1 decimal

    cursor.close()
    db.close()

    return jsonify({"promedio": promedio, "total": len(calificaciones)})
    
@app.route("/likeComentario", methods=["POST"])
def like_comentario():
    data = request.get_json()
    id = data["id"]
    like = data["like"]

    db = get_connection()
    cursor = db.cursor()

    cursor.execute("UPDATE calificacion SET likes = likes + 1 WHERE id_calificacion_tienda = %s", (id,))
    db.commit()

    return jsonify({"mensaje": f"Like sumado al comentario {id} con calificación {like}"}), 200

@app.route("/comentarTienda", methods=["POST"])
def comentarTienda():
    data = request.get_json()
    id_tienda = data.get("id_tienda")
    id_dueno = data.get("id_dueno")
    comentario = data.get("comentario")
    calificacion = data.get("calificacion")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor = db.cursor()
    sql = """
            INSERT INTO calificacion (
            id_tienda, id_dueno, opinion, calificacion
            )
            VALUES (%s, %s, %s, %s)
        """
    cursor.execute(sql, (id_tienda, id_dueno, comentario, calificacion))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Comentario registrado"}), 200


@app.route("/eliminarcomentarioTienda", methods=["DELETE"])
def eliminar_comentarioTienda():
    data = request.get_json()
    idComentario = data.get("idComentario")
    
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    cursor.execute(
        "DELETE FROM calificacion WHERE id_calificacion_tienda = %s",
        (idComentario,)  # <-- la coma es OBLIGATORIA
    )
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"mensaje": "Comentario eliminado"}), 200

@app.route("/editarcomentarioTienda", methods=["PUT"])
def editar_comentarioTienda():
    data = request.get_json()

    idComentario = data.get("id_calificacion_tienda")
    calificacion = data.get("calificacion")
    comentario = data.get("comentario")

    if not idComentario:
        return jsonify({"error": "Falta el id del comentario"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión con la base de datos"}), 500

    cursor = db.cursor()
    cursor.execute("""
        UPDATE calificacion 
        SET calificacion = %s, opinion = %s
        WHERE id_calificacion_tienda  = %s
    """, (calificacion, comentario, idComentario))

    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Comentario actualizado"}), 200



@app.route("/mipaseador", methods=["POST"])
def obtenerMipaseador():
    data = request.get_json()
    id_paseador = data.get("id_paseador")

    if not id_paseador:
        return jsonify({"error": "Falta el id"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM `paseador` WHERE id_paseador = %s;", (id_paseador,))
    resultados = cursor.fetchall()
    cursor.close()
    db.close()
    
    def convertir_tiempo(valor):
        """Convierte timedelta o time a 'HH:MM'"""
        if isinstance(valor, timedelta):
            total_seconds = int(valor.total_seconds())
            horas = total_seconds // 3600
            minutos = (total_seconds % 3600) // 60
            return f"{horas:02d}:{minutos:02d}"
        elif isinstance(valor, time):
            return valor.strftime("%H:%M")
        return valor  # si ya es string o None

    # 🔁 Convertir todos los campos de tipo timedelta/time
    for paseador in resultados:
        for k, v in paseador.items():
            paseador[k] = convertir_tiempo(v)

    return jsonify({"paseador": resultados})

@app.route("/miveterinaria", methods=["POST"])
def obtenerMiveterinaria():
    data = request.get_json()
    id = data.get("id")

    if not id:
        return jsonify({"error": "Falta la cédula"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM `veterinaria` WHERE id_veterinaria = %s;", (id,))
    resultados = cursor.fetchall()
    cursor.close()
    db.close()
    
    def convertir_tiempo(valor):
        """Convierte timedelta o time a 'HH:MM'"""
        if isinstance(valor, timedelta):
            total_seconds = int(valor.total_seconds())
            horas = total_seconds // 3600
            minutos = (total_seconds % 3600) // 60
            return f"{horas:02d}:{minutos:02d}"
        elif isinstance(valor, time):
            return valor.strftime("%H:%M")
        return valor  # si ya es string o None

    # 🔁 Convertir todos los campos de tipo timedelta/time
    for veterinaria in resultados:
        for k, v in veterinaria.items():
           veterinaria[k] = convertir_tiempo(v)

    return jsonify({"veterinaria": resultados})


@app.route("/tiendas", methods=["GET"])
def obtener_tiendas():
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM tienda;")
    resultados = cursor.fetchall()
    cursor.close()
    db.close()

    def convertir_tiempo(valor):
        """Convierte timedelta o time a 'HH:MM'"""
        if isinstance(valor, timedelta):
            total_seconds = int(valor.total_seconds())
            horas = total_seconds // 3600
            minutos = (total_seconds % 3600) // 60
            return f"{horas:02d}:{minutos:02d}"
        elif isinstance(valor, time):
            return valor.strftime("%H:%M")
        return valor

    for tienda in resultados:
        for k, v in tienda.items():
            tienda[k] = convertir_tiempo(v)

    return jsonify({"tienda": resultados})

@app.route("/veterinarias", methods=["GET"])
def obtener_veterinarias():
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM veterinaria;")
    resultados = cursor.fetchall()
    cursor.close()
    db.close()

    def convertir_tiempo(valor):
        """Convierte timedelta o time a 'HH:MM'"""
        if isinstance(valor, timedelta):
            total_seconds = int(valor.total_seconds())
            horas = total_seconds // 3600
            minutos = (total_seconds % 3600) // 60
            return f"{horas:02d}:{minutos:02d}"
        elif isinstance(valor, time):
            return valor.strftime("%H:%M")
        return valor

    for tienda in resultados:
        for k, v in tienda.items():
            tienda[k] = convertir_tiempo(v)

    return jsonify({"veterinaria": resultados})

@app.route("/paseadores", methods=["GET"])
def obtener_paseadores():
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM paseador;")
    resultados = cursor.fetchall()
    cursor.close()
    db.close()

    def convertir_tiempo(valor):
        """Convierte timedelta o time a 'HH:MM'"""
        if isinstance(valor, timedelta):
            total_seconds = int(valor.total_seconds())
            horas = total_seconds // 3600
            minutos = (total_seconds % 3600) // 60
            return f"{horas:02d}:{minutos:02d}"
        elif isinstance(valor, time):
            return valor.strftime("%H:%M")
        return valor

    for tienda in resultados:
        for k, v in tienda.items():
            tienda[k] = convertir_tiempo(v)

    return jsonify({"paseador": resultados})


@app.route("/registrarVeterinaria", methods=["POST"])
def registrarVeterinaria():
    data = request.get_json()

    cedulaUsuario = data.get("cedulaUsuario")
    imagen = data.get("imagen")
    nombre_veterinaria = data.get("nombre_veterinaria")
    descripcion = data.get("descripcion")
    experiencia = data.get("experiencia")
    direccion = data.get("direccion")
    telefono = data.get("telefono")
    domicilio = data.get("domicilio")
    horariolunesviernes = data.get("horariolunesviernes")
    cierrelunesviernes = data.get("cierrelunesviernes")
    horariosabado = data.get("horariosabado")
    cierrehorasabado = data.get("cierrehorasabado")
    horariodomingos = data.get("horariodomingos")
    cierredomingos = data.get("cierredomingos")
    metodopago = data.get("metodopago")
    certificado = data.get("certificado")
    tarifa = data.get("tarifa")
    correo = data.get("correo")
    contrasena = data.get("contrasena")
    departamento = data.get("departamento")
    ciudad = data.get("ciudad")

    # 🔐 Encriptar contraseña
    contrasena_cifrada = bcrypt.hashpw(contrasena.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # 🚨 Validar campos obligatorios
    if not all([cedulaUsuario, nombre_veterinaria, direccion, experiencia, telefono, domicilio,
                horariolunesviernes, cierrelunesviernes, horariosabado, cierrehorasabado,
                metodopago, tarifa, correo, contrasena, departamento, ciudad]):
        return jsonify({"error": "⚠️ Faltan campos obligatorios"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "❌ No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # 🔍 Verificar si ya existe
    sql_verificar = "SELECT * FROM usuarios WHERE correo = %s"
    cursor.execute(sql_verificar, (correo,))
    existente = cursor.fetchone()

    if existente:
        cursor.close()
        db.close()
        return jsonify({"error": "⚠️ El usuario ya está registrado"}), 409

    try:
        # 1️⃣ Insertar en usuarios
        sql_usuario = """
            INSERT INTO usuarios (correo, contrasena, rol)
            VALUES (%s, %s, %s)
        """
        cursor.execute(sql_usuario, (correo, contrasena_cifrada, 'veterinaria'))
        db.commit()
        
        id_usuario = cursor.lastrowid

        # 2️⃣ Insertar en veterinaria
        sql_vet = """
            INSERT INTO veterinaria (
                id_veterinaria, cedula_usuario, nombre_veterinaria, imagen, tarifa, telefono, 
                descripcion, experiencia, certificados, departamento, ciudad, direccion, tipo_pago, domicilio, 
                horariolunesviernes, cierrelunesviernes, horariosabado, cierresabado, 
                horariodomingo, cierredomingo, correo, contrasena
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql_vet, (
            id_usuario, cedulaUsuario, nombre_veterinaria, imagen, tarifa, telefono,
            descripcion, experiencia, certificado, departamento, ciudad, direccion, metodopago, domicilio,
            horariolunesviernes, cierrelunesviernes, horariosabado, cierrehorasabado,
            horariodomingos, cierredomingos, correo, contrasena_cifrada
        ))
        db.commit()

        id_veterinaria = cursor.lastrowid

        cursor.close()
        db.close()

        return jsonify({
            "mensaje": "✅ Veterinaria registrada correctamente",
            "miveterinaria": {
                "id_veterinaria": id_veterinaria,
                "nombre_veterinaria": nombre_veterinaria,
                "telefono": telefono,
                "direccion": direccion,
                "correo": correo
            }
        }), 201

    except Exception as e:
        cursor.close()
        db.close()
        return jsonify({"error": f"❌ Error al registrar: {str(e)}"}), 500
    
@app.route("/actualizar_imagen_veterinaria", methods=["PUT"])
def actualizar_imagen_veterinaria():
    data = request.get_json()
    id = data.get("id")
    imagen = data.get("imagen")

    if not id or not imagen:
        return jsonify({"error": "Faltan datos"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE veterinaria SET imagen = %s WHERE id_veterinaria = %s"
    cursor.execute(sql, (imagen, id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Imagen actualizada correctamente"}), 200


@app.route("/comentariosVeterinaria", methods=["POST"])
def obtener_comentariosVeterinaria():
    data = request.get_json()
    print("DATA RECIBIDA:", data)
    id_veterinaria = data.get("id_veterinaria")

    if not id_veterinaria:
        return jsonify({"error": "Falta el id veterinaria"}), 400
    
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    sql = """
        SELECT c.*, u.nombre, u.apellido, u.foto_perfil
        FROM calificacion_veterinaria c
        JOIN dueno_mascotas u ON c.id_dueno = u.id_dueno
        WHERE c.id_veterinaria = %s
    """
    cursor.execute(sql, (id_veterinaria,))
    calificacion = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify({"calificacion": calificacion}), 200


@app.route("/promedioVeterinaria", methods=["POST"])
def promedio_veterinaria():
    datos = request.get_json()
    id_veterinaria = datos.get("id_veterinaria")

    db = get_connection()
    cursor = db.cursor(dictionary=True)

    # Obtenemos todas las calificaciones y el promedio
    sql = "SELECT calificacion FROM calificacion_veterinaria WHERE id_veterinaria = %s"
    cursor.execute(sql, (id_veterinaria,))
    calificaciones = cursor.fetchall()

    if not calificaciones:
        promedio = 0
    else:
        suma = sum([c["calificacion"] for c in calificaciones])
        promedio = round(suma / len(calificaciones), 1)  # promedio con 1 decimal

    cursor.close()
    db.close()

    return jsonify({"promedio": promedio, "total": len(calificaciones)})
    
@app.route("/likeComentarioVeterinaria", methods=["POST"])
def like_comentarioVeterinaria():
    data = request.get_json()
    id = data["id"]
    like = data["like"]

    db = get_connection()
    cursor = db.cursor()

    cursor.execute("UPDATE calificacion_veterinaria SET likes = likes + 1 WHERE id_calificacion_veterinaria = %s", (id,))
    db.commit()

    return jsonify({"mensaje": f"Like sumado al comentario {id} con calificación {like}"}), 200

@app.route("/comentarVeterinaria", methods=["POST"])
def comentarVeterinaria():
    data = request.get_json()
    id_veterinaria = data.get("id_veterinaria")
    id_dueno = data.get("id_dueno")
    comentario = data.get("comentario")
    calificacion = data.get("calificacion")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor = db.cursor()
    sql = """
            INSERT INTO calificacion_veterinaria (
            id_veterinaria, id_dueno, opinion, calificacion
            )
            VALUES (%s, %s, %s, %s)
        """
    cursor.execute(sql, (id_veterinaria, id_dueno, comentario, calificacion))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Comentario registrado"}), 200


@app.route("/eliminarcomentarioVeterinaria", methods=["DELETE"])
def eliminar_comentarioVeterinaria():
    data = request.get_json()
    idComentario = data.get("idComentario")
    
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    cursor.execute(
        "DELETE FROM calificacion_veterinaria WHERE id_calificacion_veterinaria = %s",
        (idComentario,)  # <-- la coma es OBLIGATORIA
    )
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"mensaje": "Comentario eliminado"}), 200

@app.route("/editarcomentarioVeterinaria", methods=["PUT"])
def editar_comentarioVeterinaria():
    data = request.get_json()

    idComentario = data.get("id_calificacion_veterinaria")
    calificacion = data.get("calificacion")
    comentario = data.get("comentario")

    if not idComentario:
        return jsonify({"error": "Falta el id del comentario"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión con la base de datos"}), 500

    cursor = db.cursor()
    cursor.execute("""
        UPDATE calificacion_veterinaria 
        SET calificacion = %s, opinion = %s
        WHERE id_calificacion_veterinaria = %s
    """, (calificacion, comentario, idComentario))

    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Comentario actualizado"}), 200

@app.route("/registrarProducto", methods=["POST"])
def registrar_producto():
    data = request.get_json()
    tienda_id = data.get("tienda_id")
    nombre = data.get("nombre")
    precio = data.get("precio")
    cantidad = data.get("cantidad")
    descripcion = data.get("descripcion")
    imagen = data.get("imagen")


    if not all([nombre, precio, cantidad, imagen]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # Insertar higiene
    sql = """
        INSERT INTO producto (tienda_id, nombre, descripcion, precio, cantidad_disponible, imagen)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    valores = (tienda_id, nombre, descripcion, precio, cantidad, imagen)
    cursor.execute(sql, valores)
    db.commit()

    id_producto = cursor.lastrowid
    
    cursor.close()
    db.close()
    return jsonify({
        "mensaje": "Producto registrada correctamente",
        "producto": {
            "id_producto": id_producto,
            "tienda_id": tienda_id,
            "nombre": nombre,
            "descripcion": descripcion,
            "precio": precio,
            "cantidad_disponible":cantidad,
            "imagen": imagen,
        }
    }), 201
    
@app.route("/misproductos", methods=["POST"])
def obtenerProductos():
    data = request.get_json()
    id_tienda = data.get("id_tienda")
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    sql = "SELECT * FROM producto WHERE tienda_id = %s"
    cursor.execute(sql, (id_tienda,))

    producto = cursor.fetchall()
    cursor.close()
    db.close()

    return jsonify({"producto": producto})
    
@app.route("/citasVeterinaria", methods=["POST"])
def obtenerCitas_veterinaria():
    data = request.get_json()
    id_veterinaria = data.get("id_veterinaria")

    if not id_veterinaria:
        return jsonify({"error": "Falta el id"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id_cita_veterinaria, id_mascota, id_dueno, motivo, fecha, hora, estado, metodo_pago FROM `cita_veterinaria` WHERE id_veterinaria = %s;", (id_veterinaria,))
    resultados = cursor.fetchall()
    cursor.close()
    db.close()
    
    resultados_serializables = []
    for r in resultados:
        # Convertir fecha y horas a string
        r['fecha'] = r['fecha'].isoformat() if isinstance(r['fecha'], datetime) else str(r['fecha'])
        r['hora'] = r['hora'].strftime('%H:%M:%S') if isinstance(r['hora'], datetime) else str(r['hora'])


        resultados_serializables.append(r)
        
    return jsonify({"citas": resultados_serializables})

@app.route("/obtenerUsuario", methods=["POST"])
def obtenerUsuario():
    data = request.get_json()
    print("📥 ID recibido:", data)
    id_dueno = data.get("id_dueno")

    if not  id_dueno:
        return jsonify({"error": "Falta el id"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM `dueno_mascotas` WHERE id_dueno = %s;", (id_dueno,))
    resultados = cursor.fetchall()
    cursor.close()
    db.close()

    return jsonify({"usuario": resultados})

@app.route("/aceptar_cita_medica", methods=["PUT"])
def aceptar_cita_medica():
    data = request.get_json()
    id = data.get("id")
    fecha = data.get("fecha")
    hora = data.get("hora")

    def vacio(x): return x is None or str(x).strip() == ""
    if any(vacio(c) for c in [id,  fecha, hora]):
        return jsonify({"error": "Faltan datos"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE cita_veterinaria SET fecha = %s, hora = %s, estado = 'Aceptada' WHERE id_cita_veterinaria = %s"
    cursor.execute(sql, (fecha, hora, id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Cita aceptada correctamente"}), 200

@app.route("/cancelar_cita_medica", methods=["PUT"])
def cancelar_cita_medica():
    data = request.get_json()
    id = data.get("id")

    def vacio(x): return x is None or str(x).strip() == ""
    if any(vacio(c) for c in [id]):
        return jsonify({"error": "Faltan datos"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE cita_veterinaria SET estado = 'Cancelada' WHERE id_cita_veterinaria = %s"
    cursor.execute(sql, (id,))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Cita cancelada correctamente"}), 200

@app.route("/actualizarTienda", methods=["PUT"])
def actualizar_tienda():
    try:
        data = request.get_json()
        print("📩 Datos recibidos:", data)  
        id = data.get("id")
        cedulaUsuario = data.get("cedulaUsuario")
        imagen = data.get("imagen")
        nombre_negocio = data.get("nombre_negocio")
        descripcion = data.get("descripcion")
        direccion = data.get("direccion")
        telefono = data.get("telefono")
        domicilio = data.get("domicilio")
        horariolunesviernes = data.get("horariolunesviernes")
        cierrelunesviernes = data.get("cierrelunesviernes")
        horariosabado = data.get("horariosabado")
        cierrehorasabado = data.get("cierrehorasabado")
        horariodomingos = data.get("horariodomingos")
        cierredomingos = data.get("cierredomingos")
        metodopago = data.get("metodopago")
        departamento = data.get("departamento")
        ciudad = data.get("ciudad")

        if not all([id, cedulaUsuario, imagen, nombre_negocio, direccion, telefono,
                    domicilio, horariolunesviernes, cierrelunesviernes,
                    horariosabado, cierrehorasabado, metodopago, departamento, ciudad]):
            return jsonify({"error": "Faltan campos obligatorios"}), 400

        db = get_connection()
        if db is None:
            return jsonify({"error": "No hay conexión a la base de datos"}), 500

        cursor = db.cursor(dictionary=True)

        sql = """
            UPDATE tienda 
            SET imagen = %s, 
                cedula_usuario = %s, 
                nombre_negocio = %s, 
                descripcion = %s, 
                departamento = %s,
                ciudad = %s,
                direccion = %s, 
                telefono = %s, 
                domicilio = %s, 
                horariolunesviernes = %s, 
                cierrelunesviernes = %s, 
                horariosabado = %s, 
                cierresabado = %s, 
                horariodomingo = %s, 
                cierredomingo = %s, 
                metodo_pago = %s 
            WHERE idtienda = %s
        """
        valores = (imagen, cedulaUsuario, nombre_negocio, descripcion, departamento, ciudad, direccion, telefono, domicilio,
                horariolunesviernes, cierrelunesviernes, horariosabado, cierrehorasabado,
                horariodomingos, cierredomingos, metodopago, id)
        cursor.execute(sql, valores)
        db.commit()

        id_tienda = cursor.lastrowid
        
        cursor.close()
        db.close()
        return jsonify({
            "mensaje": "Tienda registrada correctamente",
            "mitienda": {
                "id_tienda": id_tienda,
                "imagen": imagen, 
                "cedulaUsuario": cedulaUsuario,
                "nombre_negocio": nombre_negocio,
                "descripcion": descripcion,
                "departamento": departamento,
                "ciudad": ciudad,
                "direccion": direccion,
                "telefono": telefono,
                "domicilio": domicilio,
                "horariolunesviernes": horariolunesviernes,
                "cierrelunesviernes": cierrelunesviernes,
                "horariosabado": horariosabado,
                "cierresabado": cierrehorasabado,
                "horariodomingos": horariodomingos,
                "cierredomingos": cierredomingos,
                "metodopago": metodopago
            
            }
        }), 200
    except Exception as e:
        print("💥 Error en actualizar_tienda:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route("/actualizarVeterinaria", methods=["PUT"])
def actualizar_veterinaria():
    try:
        data = request.get_json()
        id = data.get("id")
        cedulaUsuario = data.get("cedulaUsuario")
        imagen = data.get("imagen")
        nombre_veterinaria = data.get("nombre_veterinaria")
        descripcion = data.get("descripcion")
        experiencia = data.get("experiencia")
        direccion = data.get("direccion")
        telefono = data.get("telefono")
        domicilio = data.get("domicilio")
        horariolunesviernes = data.get("horariolunesviernes")
        cierrelunesviernes = data.get("cierrelunesviernes")
        horariosabado = data.get("horariosabado")
        cierrehorasabado = data.get("cierrehorasabado")
        horariodomingos = data.get("horariodomingos")
        cierredomingos = data.get("cierredomingos")
        metodopago = data.get("metodopago")
        certificado = data.get("certificado")
        tarifa = data.get("tarifa")
        departamento = data.get("departamento")
        ciudad = data.get("ciudad")

        if not all([cedulaUsuario, imagen, departamento, ciudad, nombre_veterinaria, direccion, experiencia, telefono, domicilio, horariolunesviernes, cierrelunesviernes, horariosabado, cierrehorasabado, metodopago, tarifa]):
            return jsonify({"error": "Faltan campos obligatorios"}), 400

        db = get_connection()
        if db is None:
            return jsonify({"error": "No hay conexión a la base de datos"}), 500

        cursor = db.cursor(dictionary=True)

        sql = """
            UPDATE veterinaria
            SET nombre_veterinaria = %s, 
                imagen = %s, 
                tarifa = %s, 
                telefono = %s, 
                descripcion = %s, 
                experiencia = %s,
                certificados = %s,
                departamento = %s,
                ciudad = %s,
                direccion = %s, 
                tipo_pago = %s,
                domicilio = %s, 
                horariolunesviernes = %s, 
                cierrelunesviernes = %s, 
                horariosabado = %s, 
                cierresabado = %s, 
                horariodomingo = %s, 
                cierredomingo = %s 
            WHERE id_veterinaria = %s
        """
        valores = (nombre_veterinaria, imagen, tarifa, telefono, descripcion, experiencia, certificado, departamento, ciudad, direccion, metodopago, domicilio,
                horariolunesviernes, cierrelunesviernes, horariosabado, cierrehorasabado,
                horariodomingos, cierredomingos, id)
        cursor.execute(sql, valores)
        db.commit()

        id_veterinaria = cursor.lastrowid
    
        cursor.close()
        db.close()
        return jsonify({
            "mensaje": "Veterinaria registrada correctamente",
            "miveterinaria": {
                "id_veterinaria": id_veterinaria,
                "cedulaUsuario": cedulaUsuario,
                "nombre_veterinaria": nombre_veterinaria,
                "imagen": imagen, 
                "tarifa": tarifa,
                "telefono": telefono,
                "descripcion": descripcion,
                "experiencia": experiencia,
                "certificado": certificado,
                "departamento": departamento,
                "ciudad": ciudad,
                "direccion": direccion,
                "metodopago": metodopago,
                "domicilio": domicilio,
                "horariolunesviernes": horariolunesviernes,
                "cierrelunesviernes": cierrelunesviernes,
                "horariosabado": horariosabado,
                "cierresabado": cierrehorasabado,
                "horariodomingos": horariodomingos,
                "cierredomingos": cierredomingos,
                }
            }), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/registrarPaseador", methods=["POST"])
def registrarPaseador():
    data = request.get_json()
    nombre = data.get("nombre")
    apellido = data.get("apellido")
    cedulaUsuario = data.get("cedulaUsuario")
    imagen = data.get("imagen")
    descripcion = data.get("descripcion")
    experiencia = data.get("experiencia")
    direccion = data.get("direccion")
    telefono = data.get("telefono")
    horariolunesviernes = data.get("horariolunesviernes")
    cierrelunesviernes = data.get("cierrelunesviernes")
    horariosabado = data.get("horariosabado")
    cierrehorasabado = data.get("cierrehorasabado")
    horariodomingos = data.get("horariodomingos")
    cierredomingos = data.get("cierredomingos")
    metodopago = data.get("metodopago")
    certificado = data.get("certificado")
    tarifa = data.get("tarifa")
    correo = data.get("correo")
    contrasena = data.get("contrasena")
    departamento = data.get("departamento")
    ciudad = data.get("ciudad")

    # 🔐 Encriptar contraseña
    contrasena_cifrada = bcrypt.hashpw(contrasena.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    if not all([nombre, apellido, cedulaUsuario, imagen, direccion, experiencia, telefono, horariolunesviernes, cierrelunesviernes, horariosabado, cierrehorasabado, metodopago, tarifa, correo, contrasena, departamento, ciudad]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # 🔍 Verificar si ya existe
    sql_verificar = "SELECT * FROM usuarios WHERE correo = %s"
    cursor.execute(sql_verificar, (correo,))
    existente = cursor.fetchone()

    if existente:
        cursor.close()
        db.close()
        return jsonify({"error": "⚠️ El usuario ya está registrado"}), 409

    try:
        # 1️⃣ Insertar en usuarios
        sql_usuario = """
            INSERT INTO usuarios (correo, contrasena, rol)
            VALUES (%s, %s, %s)
        """
        cursor.execute(sql_usuario, (correo, contrasena_cifrada, 'paseador'))
        db.commit()
        
        id_usuario = cursor.lastrowid

        # Insertar higiene
        sql = """
            INSERT INTO paseador (id_paseador, nombre, apellido, cedula_usuario, imagen, certificado, departamento, ciudad, zona_servicio, experiencia, tarifa_hora, telefono, descripcion, tipo_pago, horariolunesviernes, cierrelunesviernes, horariosabado, cierresabado, horariodomingo, cierredomingo, correo, contrasena)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        valores = (id_usuario, nombre, apellido, cedulaUsuario, imagen, certificado, departamento, ciudad, direccion, experiencia, tarifa, telefono, descripcion, metodopago, horariolunesviernes, cierrelunesviernes, horariosabado, cierrehorasabado, horariodomingos, cierredomingos, correo, contrasena_cifrada)
        cursor.execute(sql, valores)
        db.commit()

        id = cursor.lastrowid
        
        cursor.close()
        db.close()
        return jsonify({
            "mensaje": "Paseador registrada correctamente",
            "mipaseador": {
                "id_paseador": id,
        }
        }), 201
        
    except Exception as e:
        cursor.close()
        db.close()
        return jsonify({"error": f"❌ Error al registrar: {str(e)}"}), 500
    
@app.route("/actualizar_imagen_paseador", methods=["PUT"])
def actualizar_imagen_paseador():
    data = request.get_json()
    id_paseador = data.get("id_paseador")
    imagen = data.get("imagen")

    if not id_paseador or not imagen:
        return jsonify({"error": "Faltan datos"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE paseador SET imagen = %s WHERE id_paseador = %s"
    cursor.execute(sql, (imagen, id_paseador))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Imagen actualizada correctamente"}), 200
    
@app.route("/promedioPaseador", methods=["POST"])
def promedio_paseador():
    datos = request.get_json()
    id_paseador = datos.get("id_paseador")

    db = get_connection()
    cursor = db.cursor(dictionary=True)

    # Obtenemos todas las calificaciones y el promedio
    sql = "SELECT calificacion FROM calificacion_paseador WHERE id_paseador = %s"
    cursor.execute(sql, (id_paseador,))
    calificaciones = cursor.fetchall()

    if not calificaciones:
        promedio = 0
    else:
        suma = sum([c["calificacion"] for c in calificaciones])
        promedio = round(suma / len(calificaciones), 1)  # promedio con 1 decimal

    cursor.close()
    db.close()

    return jsonify({"promedio": promedio, "total": len(calificaciones)})

@app.route("/comentariosPaseador", methods=["POST"])
def obtener_comentariosPaseador():
    data = request.get_json()
    id_paseador = data.get("id_paseador")

    if not id_paseador:
        return jsonify({"error": "Falta el id"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    sql = """
        SELECT c.*, u.nombre, u.apellido, u.foto_perfil
        FROM calificacion_paseador c
        JOIN dueno_mascotas u ON c.id_dueno = u.id_dueno
        WHERE c.id_paseador = %s
    """
    cursor.execute(sql, (id_paseador,))
    calificacion = cursor.fetchall()
    cursor.close()
    db.close()

    return jsonify({"calificacion": calificacion}), 200


@app.route("/likeComentarioPaseador", methods=["POST"])
def like_comentarioPaseador():
    data = request.get_json()
    id = data["id"]
    like = data["like"]

    db = get_connection()
    cursor = db.cursor()

    cursor.execute("UPDATE calificacion_paseador SET likes = likes + 1 WHERE id_calificacion_paseador = %s", (id,))
    db.commit()

    return jsonify({"mensaje": f"Like sumado al comentario {id} con calificación {like}"}), 200

@app.route("/paseosPaseador", methods=["POST"])
def obtenerCitas_Paseador():
    data = request.get_json()
    id_paseador = data.get("id_paseador")

    if not id_paseador:
        return jsonify({"error": "Falta la cédula"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT idpaseo, id_mascota, id_dueno, metodo_pago, fecha, hora_inicio, hora_fin, punto_encuentro, total, comportamiento, estado FROM `paseo` WHERE id_paseador = %s;", (id_paseador,))
    resultados = cursor.fetchall()
    cursor.close()
    db.close()

    resultados_serializables = []
    for r in resultados:
        # Convertir fecha y horas a string
        r['fecha'] = r['fecha'].isoformat() if isinstance(r['fecha'], datetime) else str(r['fecha'])
        r['hora_inicio'] = r['hora_inicio'].strftime('%H:%M:%S') if isinstance(r['hora_inicio'], datetime) else str(r['hora_inicio'])
        r['hora_fin'] = r['hora_fin'].strftime('%H:%M:%S') if isinstance(r['hora_fin'], datetime) else (str(r['hora_fin']) if r['hora_fin'] else "N/A")

        # Convertir timedelta a int (minutos)
        if r['hora_fin'] != "N/A":
            hi = datetime.strptime(r['hora_inicio'], "%H:%M:%S")
            hf = datetime.strptime(r['hora_fin'], "%H:%M:%S")
            duracion = hf - hi
            r['duracion_minutos'] = int(duracion.total_seconds() // 60)  # <-- ya no es timedelta
        else:
            r['duracion_minutos'] = None

        resultados_serializables.append(r)

    return jsonify({"paseos": resultados_serializables})

@app.route("/aceptar_paseo", methods=["PUT"])
def aceptar_paseo():
    data = request.get_json()
    id = data.get("id")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE paseo SET estado = %s WHERE idpaseo = %s"
    cursor.execute(sql, ("Aceptado", id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Paseo aceptado correctamente"}), 200

@app.route("/cancelar_paseo", methods=["PUT"])
def cancelar_paseo():
    data = request.get_json()
    id = data.get("id")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE paseo SET estado = %s WHERE idpaseo = %s"
    cursor.execute(sql, ("Cancelado", id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Paseo cancelado correctamente"}), 200


@app.route("/actualizarPaseador", methods=["PUT"])
def actualizar_Paseador():
    try:
        data = request.get_json()
        id_paseador = data.get("id_paseador")
        nombre = data.get("nombre")
        apellido = data.get("apellido")
        cedulaUsuario = data.get("cedulaUsuario")
        imagen = data.get("imagen")
        tarifa = data.get("tarifa")
        descripcion = data.get("descripcion")
        experiencia = data.get("experiencia")
        direccion = data.get("direccion")
        telefono = data.get("telefono")
        horariolunesviernes = data.get("horariolunesviernes")
        cierrelunesviernes = data.get("cierrelunesviernes")
        horariosabado = data.get("horariosabado")
        cierrehorasabado = data.get("cierrehorasabado")
        horariodomingos = data.get("horariodomingos")
        cierredomingos = data.get("cierredomingos")
        metodopago = data.get("metodopago")
        certificado = data.get("certificado")
        departamento = data.get("departamento")
        ciudad = data.get("ciudad")


        if not all([nombre, apellido, cedulaUsuario, imagen, direccion, experiencia, telefono, horariolunesviernes, cierrelunesviernes, horariosabado, cierrehorasabado, metodopago, tarifa, ciudad, departamento]):
            return jsonify({"error": "Faltan campos obligatorios"}), 400

        db = get_connection()
        if db is None:
            return jsonify({"error": "No hay conexión a la base de datos"}), 500

        cursor = db.cursor(dictionary=True)

        sql = """
            UPDATE paseador
            SET nombre = %s,
                apellido = %s,
                cedula_usuario = %s,
                imagen = %s,
                certificado = %s, 
                departamento = %s,
                ciudad = %s,
                zona_servicio = %s,
                experiencia = %s,
                telefono = %s, 
                descripcion = %s, 
                tarifa_hora = %s, 
                tipo_pago = %s,
                horariolunesviernes = %s, 
                cierrelunesviernes = %s, 
                horariosabado = %s, 
                cierresabado = %s, 
                horariodomingo = %s, 
                cierredomingo = %s 
            WHERE id_paseador = %s
        """
        valores = (nombre, apellido, cedulaUsuario, imagen, certificado, departamento, ciudad, direccion, experiencia, telefono, descripcion, tarifa, metodopago,
                horariolunesviernes, cierrelunesviernes, horariosabado, cierrehorasabado,
                horariodomingos, cierredomingos, id_paseador)
        cursor.execute(sql, valores)
        db.commit()

        cursor.close()
        db.close()
        return jsonify({
            "mensaje": "Paseador editado correctamente",
            "miveterinaria": {
                "cedulaUsuario": cedulaUsuario,
                "imagen": imagen, 
                "tarifa": tarifa,
                "telefono": telefono,
                "descripcion": descripcion,
                "experiencia": experiencia,
                "certificado": certificado,
                "departamento": departamento,
                "ciudad": ciudad,
                "direccion": direccion,
                "metodopago": metodopago,
                "horariolunesviernes": horariolunesviernes,
                "cierrelunesviernes": cierrelunesviernes,
                "horariosabado": horariosabado,
                "cierresabado": cierrehorasabado,
                "horariodomingos": horariodomingos,
                "cierredomingos": cierredomingos,
                }
            }), 200
    
    except Exception as e:
        print("💥 Error en actualizar_tienda:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route("/comentarPaseador", methods=["POST"])
def comentarPaseador():
    data = request.get_json()
    id_paseador = data.get("id_paseador")
    id_dueno = data.get("id_dueno")
    comentario = data.get("comentario")
    calificacion = data.get("calificacion")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor = db.cursor()
    sql = """
            INSERT INTO calificacion_paseador (
            id_paseador, id_dueno, opinion, calificacion
            )
            VALUES (%s, %s, %s, %s)
        """
    cursor.execute(sql, (id_paseador, id_dueno, comentario, calificacion))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Comentario registrado"}), 200


@app.route("/eliminarcomentarioPaseador", methods=["DELETE"])
def eliminar_comentarioPaseador():
    data = request.get_json()
    idComentario = data.get("idComentario")
    
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    cursor.execute(
        "DELETE FROM calificacion_paseador WHERE id_calificacion_paseador = %s",
        (idComentario,)  # <-- la coma es OBLIGATORIA
    )
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"mensaje": "Comentario eliminado"}), 200

@app.route("/editarcomentarioPaseador", methods=["PUT"])
def editar_comentarioPaseador():
    data = request.get_json()

    idComentario = data.get("id_calificacion_paseador")
    calificacion = data.get("calificacion")
    comentario = data.get("comentario")

    if not idComentario:
        return jsonify({"error": "Falta el id del comentario"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión con la base de datos"}), 500

    cursor = db.cursor()
    cursor.execute("""
        UPDATE calificacion_paseador 
        SET calificacion = %s, opinion = %s
        WHERE id_calificacion_paseador  = %s
    """, (calificacion, comentario, idComentario))

    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Comentario actualizado"}), 200


@app.route("/eliminarProducto", methods=["POST"])
def eliminar_producto():
    data = request.get_json()
    id_producto = data["id_producto"]
    id_tienda = data["id_tienda"]

    db = get_connection()
    cursor = db.cursor()

    sql = "DELETE FROM producto WHERE idproducto = %s AND tienda_id = %s"
    valores = (id_producto, id_tienda)

    cursor.execute(sql, valores)
    db.commit()

    return jsonify({"mensaje": f"Producto eliminado con éxito"}), 200

@app.route("/actualizarProducto", methods=["PUT"])
def actualizar_producto():
    data = request.get_json()
    idproducto = data.get("idproducto")
    tienda_id = data.get("tienda_id")
    nombre = data.get("nombre")
    precio = data.get("precio")
    cantidad = data.get("cantidad")
    descripcion = data.get("descripcion")
    imagen = data.get("imagen")
    
    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE producto SET nombre = %s, descripcion = %s, precio = %s, cantidad_disponible = %s, imagen = %s WHERE idproducto = %s AND tienda_id = %s"
    cursor.execute(sql, (nombre, descripcion, precio, cantidad, imagen, idproducto, tienda_id,))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Producto editado correctamente"}), 200

@app.route("/registrarPaseo", methods=["POST"])
def registrarPaseo():
    data = request.get_json()
    print("📩 Datos recibidos:", data)
    id_mascota = data.get("id_mascota")
    id_dueno = data.get("id_dueno")
    id_paseador = data.get("id_paseador")
    direccion = data.get("direccion")
    horarioInicio = data.get("horarioInicio")
    cierrefin = data.get("cierrefin")
    metodopago = data.get("metodopago")
    tarifa = data.get("tarifa")
    fecha = data.get("fecha")

    if not all([id_mascota, id_dueno, id_paseador, direccion, horarioInicio, cierrefin, metodopago, tarifa, fecha]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    try:
        # 1️⃣ Insertar en usuarios
        sql_usuario = """
            INSERT INTO paseo (id_paseador, id_mascota, id_dueno, metodo_pago, fecha, hora_inicio, hora_fin, total, punto_encuentro, estado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql_usuario, (id_paseador, id_mascota, id_dueno, metodopago, fecha, horarioInicio, cierrefin, tarifa, direccion, 'pendiente'))
        db.commit()

        cursor.close()
        db.close()
        return jsonify({
            "mensaje": "Paseo registrado correctamente",
        }), 201
        
    except Exception as e:
        cursor.close()
        db.close()
        return jsonify({"error": f"❌ Error al registrar: {str(e)}"}), 500

@app.route("/registrarCitaVeterinaria", methods=["POST"])
def registrarCita():
    data = request.get_json()
    print("📩 Datos recibidos:", data)
    id_mascota = data.get("id_mascota")
    id_dueno = data.get("id_dueno")
    id_veterinaria = data.get("id_veterinaria")
    motivo = data.get("motivo")
    metodopago = data.get("metodopago")


    if not all([id_mascota, id_dueno, id_veterinaria, motivo, metodopago]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    try:
        # 1️⃣ Insertar en usuarios
        sql_usuario = """
            INSERT INTO cita_veterinaria (id_mascota, id_dueno, motivo, estado, id_veterinaria, metodo_pago)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql_usuario, (id_mascota, id_dueno, motivo, 'pendiente', id_veterinaria, metodopago))
        db.commit()

        cursor.close()
        db.close()
        return jsonify({
            "mensaje": "Cita registrada correctamente",
        }), 201
        
    except Exception as e:
        cursor.close()
        db.close()
        return jsonify({"error": f"❌ Error al registrar: {str(e)}"}), 500

@app.route("/no_asistio_paseo", methods=["PUT"])
def no_asistio_paseo():
    data = request.get_json()
    id = data.get("id")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE paseo SET estado = %s WHERE idpaseo = %s"
    cursor.execute(sql, ("No asistió", id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Paseo marcado como 'No asistió' correctamente"}), 200

@app.route("/finalizado_paseo", methods=["PUT"])
def finalizado_paseo():
    data = request.get_json()
    id = data.get("id")
    comentario = data.get("comentario")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE paseo SET estado = %s, comportamiento = %s WHERE idpaseo = %s"
    cursor.execute(sql, ("Finalizado", comentario, id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Paseo finalizado correctamente"}), 200

@app.route("/no_asistio_cita", methods=["PUT"])
def no_asistio_cita():
    data = request.get_json()
    id = data.get("id")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE cita_veterinaria SET estado = %s WHERE id_cita_veterinaria = %s"
    cursor.execute(sql, ("No asistió", id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Paseo marcado como 'No asistió' correctamente"}), 200

@app.route("/finalizada_cita", methods=["PUT"])
def finalizado_cita():
    data = request.get_json()
    id = data.get("id")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE cita_veterinaria SET estado = %s WHERE id_cita_veterinaria = %s"
    cursor.execute(sql, ("Finalizada", id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Cita finalizada correctamente"}), 200

@app.route("/historialClinico", methods=["POST"])
def historialClinico():
    data = request.get_json()
    id_mascota = data.get("id_mascota")

    if not id_mascota:
        return jsonify({"error": "Falta el ID de la mascota"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    sql = """
        SELECT 
            h.idhistorial_medico,
            h.id_mascota,
            h.id_veterinaria,
            h.nombre_veterinaria,
            h.peso,
            h.fecha,
            h.hora,
            h.motivo_consulta,
            h.diagnostico,
            h.tratamiento,
            h.observaciones,
            v.nombre_veterinaria AS nombre_vet_bd
        FROM historial_medico h
        LEFT JOIN veterinaria v ON v.id_veterinaria = h.id_veterinaria
        WHERE h.id_mascota = %s;
    """
    cursor.execute(sql, (id_mascota,))
    historia = cursor.fetchall()
    cursor.close()
    db.close()
    for h in historia:
        if isinstance(h.get("hora"), timedelta):
            total_seconds = int(h["hora"].total_seconds())
            horas = total_seconds // 3600
            minutos = (total_seconds % 3600) // 60
            h["hora"] = f"{horas:02d}:{minutos:02d}"
        elif isinstance(h.get("hora"), time):
            h["hora"] = h["hora"].strftime("%H:%M")
        
        if isinstance(h.get("fecha"), date):
            h["fecha"] = h["fecha"].strftime("%Y-%m-%d")

    return jsonify({"historia": historia}), 200

@app.route('/eliminar_historial', methods=['DELETE'])
def eliminar_historial():
    data = request.get_json()
    id_historial = data.get("id_historial")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500
    # Aquí haces la lógica para eliminar el registro de higiene
    cursor = db.cursor(dictionary=True)
    cursor.execute("DELETE FROM historial_medico WHERE idhistorial_medico = %s", (id_historial,))
    db.commit()

    return jsonify({"mensaje": "Historial eliminado correctamente"}), 200

@app.route("/registrarHistorial", methods=["POST"])
def registrar_historial():
    data = request.get_json()
    id_mascota = data.get("id_mascota")
    id_veterinaria = data.get("id_veterinaria")
    fecha = data.get("fecha")
    hora = data.get("hora")
    nombre_veterinaria = data.get("nombre_veterinaria")
    peso = data.get("peso")
    motivo = data.get("motivo")
    diagnostico = data.get("diagnostico")
    tratamiento = data.get("tratamiento")
    observaciones = data.get("observaciones")

    if not all([fecha, hora, nombre_veterinaria, peso, motivo, diagnostico, tratamiento, observaciones, id_mascota]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # Insertar higiene
    sql = """
        INSERT INTO historial_medico (id_mascota, id_veterinaria, nombre_veterinaria, peso, fecha, hora, motivo_consulta, diagnostico, tratamiento, observaciones)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    valores = (id_mascota, id_veterinaria, nombre_veterinaria, peso, fecha, hora, motivo, diagnostico, tratamiento, observaciones)
    cursor.execute(sql, valores)
    db.commit()
    
    cursor.close()
    db.close()
    return jsonify({
        "mensaje": "Historial clínico registrada correctamente",
    }), 201
    
@app.route("/editarHistorial", methods=["PUT"])
def editar_historial():
    data = request.get_json()
    id_mascota = data.get("id_mascota")
    id_historial = data.get("id_historial")
    fecha = data.get("fecha")
    hora = data.get("hora")
    nombre_veterinaria = data.get("nombre_veterinaria")
    peso = data.get("peso")
    motivo = data.get("motivo")
    diagnostico = data.get("diagnostico")
    tratamiento = data.get("tratamiento")
    observaciones = data.get("observaciones")

    if not all([fecha, hora, nombre_veterinaria, peso, motivo, diagnostico, tratamiento, observaciones, id_mascota]):
        return jsonify({"error": "Faltan campos obligatorios"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # Insertar higiene
    sql = """
       UPDATE historial_medico
    SET 
        id_mascota = %s,
        nombre_veterinaria = %s,
        peso = %s,
        fecha = %s,
        hora = %s,
        motivo_consulta = %s,
        diagnostico = %s,
        tratamiento = %s,
        observaciones = %s
    WHERE idhistorial_medico = %s
    """
    valores = (
        id_mascota,
        nombre_veterinaria,
        peso,
        fecha,
        hora,
        motivo,
        diagnostico,
        tratamiento,
        observaciones,
        id_historial
    )
    cursor.execute(sql, valores)
    db.commit()
    
    cursor.close()
    db.close()
    return jsonify({
        "mensaje": "Historial clínico registrada correctamente",
    }), 201
    
@app.route("/documentos", methods=["POST"])
def documentos():
    data = request.get_json()
    id_mascota = data.get("id_mascota")

    if not id_mascota:
        return jsonify({"error": "Falta el ID de la mascota"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    sql = """
        SELECT *
        FROM documentos
        WHERE id_mascotas = %s;
    """
    cursor.execute(sql, (id_mascota,))
    documentos = cursor.fetchall()
    cursor.close()
    db.close()

    return jsonify({"documentos": documentos}), 200


@app.route("/registrarDocumento", methods=["POST"])
def registraDocumentos():
    data = request.get_json()
    id_mascota = data.get("id_mascota")
    nombre_documento = data.get("nombre_documento")
    certificado = data.get("certificado")

    if not all([id_mascota, nombre_documento, certificado]):
        return jsonify({"error": "⚠️ Faltan campos obligatorios"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "❌ No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    try:
        # 1️⃣ Insertar en usuarios
        sql_usuario = """
            INSERT INTO documentos (id_mascotas, nombre, imagen)
            VALUES (%s, %s, %s)
        """
        cursor.execute(sql_usuario, (id_mascota, nombre_documento, certificado))
        db.commit()

        cursor.close()
        db.close()

        return jsonify({
            "mensaje": "✅ Documento registrado correctamente",
        }), 201

    except Exception as e:
        cursor.close()
        db.close()
        return jsonify({"error": f"❌ Error al registrar: {str(e)}"}), 500
    
@app.route('/eliminar_documento', methods=['DELETE'])
def eliminar_documento():
    data = request.get_json()
    id_documento = data.get("id_documento")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500
    # Aquí haces la lógica para eliminar el registro de higiene
    cursor = db.cursor(dictionary=True)
    cursor.execute("DELETE FROM documentos WHERE id_documento = %s", (id_documento,))
    db.commit()

    return jsonify({"mensaje": "Documento eliminado correctamente"}), 200

@app.route("/enviar_solicitud", methods=["POST"])
def enviar_solicitud():
    data = request.get_json()
    id_mascota = data.get("id_mascota")
    id_dueno = data.get("id_dueno")
    id_persona = data.get("id_persona")
    tipo_relacion = data.get("tipo_relacion")
    if not id_mascota:
        return jsonify({"error": "Falta el ID de la mascota"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    sql = """
        INSERT INTO solicitudes (id_remitente, id_destinatario, id_mascota, parentesco, estado) VALUES (%s, %s, %s, %s, %s)
    """
    cursor.execute(sql, (id_dueno, id_persona, id_mascota, tipo_relacion, "pendiente"))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"msg": "Solicitud enviada"}), 200


@app.route("/Comida", methods=["POST"])
def obtener_comida():
    data = request.get_json()
    id_mascota = data.get("id_mascota")

    if not id_mascota:
        return jsonify({"error": "Falta el id"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    sql = """
        SELECT *
        FROM comidas_diarias
        WHERE id_mascota = %s;
    """
    cursor.execute(sql, (id_mascota,))
    comida = cursor.fetchall()
    cursor.close()
    db.close()

    for m in comida:
        
        if m["fecha"]:
            m["fecha"] = m["fecha"].strftime("%Y-%m-%d")
    return jsonify({"comida": comida}), 200

@app.route("/GuardarComida", methods=["POST"])
def guardar_comida():
    data = request.get_json()
    id_mascota = data.get("id_mascota")
    gramos_totales_dia = data.get("gramos_totales_dia")
    agua_total_dia = data.get("agua_total_dia")

    if not id_mascota:
        return jsonify({"error": "Falta el id"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # Insertar un nuevo registro
    sql_insert = """
        INSERT INTO comidas_diarias (id_mascota, gramos_totales_dia, agua_total_dia, fecha)
        VALUES (%s, %s, %s, NOW());
    """
    cursor.execute(sql_insert, (id_mascota, gramos_totales_dia, agua_total_dia))
    db.commit()

    # Consultar todos los registros de la mascota
    sql_select = """
        SELECT *
        FROM comidas_diarias
        WHERE id_mascota = %s
        ORDER BY fecha DESC;
    """
    cursor.execute(sql_select, (id_mascota,))
    comida = cursor.fetchall()

    # Formatear fecha
    for m in comida:
        if m.get("fecha"):
            m["fecha"] = m["fecha"].strftime("%Y-%m-%d %H:%M:%S")

    cursor.close()
    db.close()

    return jsonify({"comida": comida}), 200

@app.route("/ActualizarComida", methods=["PUT"])
def modificar_comida():
    data = request.get_json()
    id_mascota = data.get("id_mascota")
    gramos_totales_dia = data.get("gramos_totales_dia")
    agua_total_dia = data.get("agua_total_dia")

    if not id_mascota or gramos_totales_dia is None or agua_total_dia is None:
        return jsonify({"error": "Faltan datos obligatorios"}), 400

    try:
        gramos_totales_dia = int(gramos_totales_dia)
        agua_total_dia = int(agua_total_dia)
    except ValueError:
        return jsonify({"error": "Los totales deben ser números enteros"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # Actualizar el registro más reciente de la mascota
    sql_update = """
        UPDATE comidas_diarias
        SET gramos_totales_dia = %s, agua_total_dia = %s
        WHERE id_mascota = %s
        ORDER BY fecha DESC
        LIMIT 1;
    """
    cursor.execute(sql_update, (gramos_totales_dia, agua_total_dia, id_mascota))
    db.commit()

    # Consultar todos los registros de la mascota (opcional)
    sql_select = """
        SELECT *
        FROM comidas_diarias
        WHERE id_mascota = %s
        ORDER BY fecha DESC;
    """
    cursor.execute(sql_select, (id_mascota,))
    comida = cursor.fetchall()

    # Formatear fecha
    for m in comida:
        if m.get("fecha"):
            m["fecha"] = m["fecha"].strftime("%Y-%m-%d %H:%M:%S")

    cursor.close()
    db.close()

    return jsonify({"comida": comida}), 200


@app.route("/EditarComida", methods=["PUT"])
def editar_comida():
    data = request.get_json()
    id_mascota = data.get("id_mascota")
    fecha = data.get("fecha")  # formato: YYYY-MM-DD
    gramos = data.get("gramos", 0)

    if not id_mascota or not fecha:
        return jsonify({"error": "Faltan datos"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # Verificar si ya existe registro para esa fecha y mascota
    sql_check = """
        SELECT * FROM comidas_diarias
        WHERE id_mascota = %s AND DATE(fecha) = %s
    """
    cursor.execute(sql_check, (id_mascota, fecha))
    existing = cursor.fetchone()

    if existing:
        # Si existe, actualizar sumando
        sql_update = """
            UPDATE comidas_diarias
            SET gramos_consumidos = gramos_consumidos + %s
            WHERE id_mascota = %s AND DATE(fecha) = %s
        """
        cursor.execute(sql_update, (gramos, id_mascota, fecha))
    else:
        # Si no existe, insertar nuevo
        sql_insert = """
            INSERT INTO comidas_diarias (id_mascota, fecha, gramos_consumidos)
            VALUES (%s, %s, %s)
        """
        cursor.execute(sql_insert, (id_mascota, fecha, gramos))

    db.commit()

    # Consultar registro actualizado
    sql_select = """
        SELECT * FROM comidas_diarias
        WHERE id_mascota = %s AND DATE(fecha) = %s
    """
    cursor.execute(sql_select, (id_mascota, fecha))
    comida = cursor.fetchone()
    if comida and comida.get("fecha"):
        comida["fecha"] = comida["fecha"].strftime("%Y-%m-%d %H:%M:%S")

    cursor.close()
    db.close()

    return jsonify({"comida": comida}), 200

@app.route("/EditarAgua", methods=["PUT"])
def editar_agua():
    data = request.get_json()
    id_mascota = data.get("id_mascota")
    fecha = data.get("fecha")  # formato: YYYY-MM-DD
    agua = data.get("agua", 0)

    if not id_mascota or not fecha:
        return jsonify({"error": "Faltan datos"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    # Verificar si ya existe registro para esa fecha y mascota
    sql_check = """
        SELECT * FROM comidas_diarias
        WHERE id_mascota = %s AND DATE(fecha) = %s
    """
    cursor.execute(sql_check, (id_mascota, fecha))
    existing = cursor.fetchone()

    if existing:
        # Si existe, actualizar sumando
        sql_update = """
            UPDATE comidas_diarias
            SET agua_consumidos = agua_consumidos + %s
            WHERE id_mascota = %s AND DATE(fecha) = %s
        """
        cursor.execute(sql_update, (agua, id_mascota, fecha))
    else:
        # Si no existe, insertar nuevo
        sql_insert = """
            INSERT INTO comidas_diarias (id_mascota, fecha, agua_consumidos)
            VALUES (%s, %s, %s)
        """
        cursor.execute(sql_insert, (id_mascota, fecha, agua))

    db.commit()

    # Consultar registro actualizado
    sql_select = """
        SELECT * FROM comidas_diarias
        WHERE id_mascota = %s AND DATE(fecha) = %s
    """
    cursor.execute(sql_select, (id_mascota, fecha))
    comida = cursor.fetchone()
    if comida and comida.get("fecha"):
        comida["fecha"] = comida["fecha"].strftime("%Y-%m-%d %H:%M:%S")

    cursor.close()
    db.close()

    return jsonify({"comida": comida}), 200


@app.route("/obtener_solicitudes", methods=["POST"])
def obtener_solicitudes():
    data = request.get_json()
    id_dueno = data.get("id_dueno")
    
    if not id_dueno:
        return jsonify({"error": "Falta el ID del dueño"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    query = """
        SELECT 
        s.id_solicitud,
        s.id_mascota,
        s.parentesco,
        s.estado,
        s.id_remitente,
        m.nombre AS nombre_mascota,
        p.nombre AS nombre,
        p.apellido AS apellido,
        m.imagen_perfil
    FROM solicitudes s
    JOIN dueno_mascotas p 
        ON p.id_dueno = 
            CASE 
                WHEN s.id_remitente = %s THEN s.id_destinatario
                ELSE s.id_remitente
            END
    JOIN mascotas m 
        ON m.id_mascotas = s.id_mascota
    WHERE s.id_remitente = %s OR s.id_destinatario = %s;
    """
    cursor.execute(query, (id_dueno, id_dueno, id_dueno))

    # Obligatorio: leer resultados
    solicitudes = cursor.fetchall()
    cursor.close()
    db.close()

    return jsonify({"solicitudes": solicitudes}), 200

@app.route("/cancelar_solicitud", methods=["PUT"])
def cancelar_solicitud():
    data = request.get_json()
    id_solicitud = data.get("id_solicitud")

    if not id_solicitud:
        return jsonify({"error": "Falta el ID de la solicitud"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    sql = """
       UPDATE solicitudes
    SET 
        estado = %s
    WHERE id_solicitud = %s
    """
    valores = (
        "cancelada",
        id_solicitud
    )
    cursor.execute(sql, valores)
    db.commit()
    
    cursor.close()
    db.close()
    return jsonify({
        "mensaje": "Solicitud cancelada correctamente",
    }), 200
    
@app.route("/aceptar_solicitud", methods=["PUT"])
def aceptar_solicitud():
    data = request.get_json()
    
    id_solicitud = data.get("id_solicitud")
    id_mascota = data.get("id_mascota")
    id_dueno = data.get("id_dueno")  # ← NECESARIO

    # Validaciones
    if not id_solicitud:
        return jsonify({"error": "Falta el ID de la solicitud"}), 400
    if not id_mascota:
        return jsonify({"error": "Falta el ID de la mascota"}), 400
    if not id_dueno:
        return jsonify({"error": "Falta el ID del dueño"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    try:
        # 1. Cambiar estado de la solicitud
        sql = """
        UPDATE solicitudes
        SET estado = %s
        WHERE id_solicitud = %s
        """
        cursor.execute(sql, ("aceptada", id_solicitud))
        db.commit()

        # 2. Registrar relación dueño–mascota
        cursor.execute(
            "INSERT INTO duenosymascotas (id_mascota, id_dueno) VALUES (%s, %s)",
            (id_mascota, id_dueno)
        )
        db.commit()
    
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        db.close()

    return jsonify({
        "mensaje": "Solicitud aceptada correctamente"
    }), 200

@app.route("/obtener_mascotas_compartidas", methods=["POST"])
def obtener_mascotas_compartidas():
    data = request.get_json()
    id_dueno = data.get("id_dueno")

    if not id_dueno:
        return jsonify({"error": "Falta el ID del dueño"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)

    sql = """
        SELECT 
            d2.id_dueno AS id_otro_dueno,
            d2.nombre AS nombre_otro_dueno,
            d2.apellido AS apellido_otro_dueno,

            m.id_mascotas,
            m.nombre AS nombre_mascota,
            m.imagen_perfil AS foto_mascota,

            s.parentesco,
            s.estado AS estado_solicitud

        FROM duenosymascotas dm1

        INNER JOIN duenosymascotas dm2 
            ON dm1.id_mascota = dm2.id_mascota
            AND dm2.id_dueno != %s

        INNER JOIN dueno_mascotas d2
            ON dm2.id_dueno = d2.id_dueno

        INNER JOIN mascotas m
            ON dm1.id_mascota = m.id_mascotas

        LEFT JOIN solicitudes s
            ON (
                (s.id_remitente = dm1.id_dueno AND s.id_destinatario = dm2.id_dueno)
                OR
                (s.id_remitente = dm2.id_dueno AND s.id_destinatario = dm1.id_dueno)
            )
            AND s.id_mascota = dm1.id_mascota

        WHERE dm1.id_dueno = %s;
    """

    cursor.execute(sql, (id_dueno, id_dueno))
    mascotas = cursor.fetchall()

    cursor.close()
    db.close()

    return jsonify({"mascotas": mascotas}), 200

@app.route("/paseos_dueno", methods=["POST"])
def obtenerPaseos_usuario():
    data = request.get_json()
    id_dueno = data.get("id_dueno")

    if not id_dueno:
        return jsonify({"error": "Falta la cédula"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("""
    SELECT 
        p.idpaseo,
        p.id_mascota,
        p.id_paseador,
        p.metodo_pago,
        p.fecha,
        p.hora_inicio,
        p.hora_fin,
        p.punto_encuentro,
        p.estado,
        p.total,
        p.comportamiento,

        pa.telefono AS telefono_paseador,
        pa.nombre AS nombre_paseador,
        pa.apellido AS apellido_paseador,
        pa.imagen AS foto_paseador,

        -- Datos de la mascota
        m.nombre AS nombre_mascota

    FROM paseo p
    INNER JOIN paseador pa 
        ON p.id_paseador = pa.id_paseador

    INNER JOIN mascotas m
        ON p.id_mascota = m.id_mascotas

    WHERE p.id_dueno = %s;
    """, (id_dueno,))
    resultados = cursor.fetchall()
    cursor.close()
    db.close()

    resultados_serializables = []
    for r in resultados:
        # Convertir fecha y horas a string
        r['fecha'] = r['fecha'].isoformat() if isinstance(r['fecha'], datetime) else str(r['fecha'])
        r['hora_inicio'] = r['hora_inicio'].strftime('%H:%M:%S') if isinstance(r['hora_inicio'], datetime) else str(r['hora_inicio'])
        r['hora_fin'] = r['hora_fin'].strftime('%H:%M:%S') if isinstance(r['hora_fin'], datetime) else (str(r['hora_fin']) if r['hora_fin'] else "N/A")

        # Convertir timedelta a int (minutos)
        if r['hora_fin'] != "N/A":
            hi = datetime.strptime(r['hora_inicio'], "%H:%M:%S")
            hf = datetime.strptime(r['hora_fin'], "%H:%M:%S")
            duracion = hf - hi
            r['duracion_minutos'] = int(duracion.total_seconds() // 60)  # <-- ya no es timedelta
        else:
            r['duracion_minutos'] = None

        resultados_serializables.append(r)

    return jsonify({"paseos": resultados_serializables})

@app.route("/citas_dueno", methods=["POST"])
def obtenerCitas_usuario():
    data = request.get_json()
    id_dueno = data.get("id_dueno")

    if not id_dueno:
        return jsonify({"error": "Falta la cédula"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("""
    SELECT 
        c.id_cita_veterinaria,
        c.id_mascota,
        c.id_dueno,
        c.fecha,
        c.hora,
        c.motivo,
        c.estado,
        c.id_veterinaria,
        c.metodo_pago,
        v.nombre_veterinaria,
        v.telefono AS telefono_veterinaria,
        v.imagen AS imagen_veterinaria,

        m.nombre AS nombre_mascota

    FROM cita_veterinaria c
    LEFT JOIN veterinaria v
        ON c.id_veterinaria = v.id_veterinaria
    LEFT JOIN mascotas m
        ON c.id_mascota = m.id_mascotas

    WHERE c.id_dueno = %s;
    """, (id_dueno,))
    resultados = cursor.fetchall()
    cursor.close()
    db.close()

    resultados_serializables = []
    for r in resultados:
        # Convertir fecha y horas a string
        r['fecha'] = r['fecha'].isoformat() if isinstance(r['fecha'], datetime) else str(r['fecha'])
        r['hora'] = r['hora'].strftime('%H:%M:%S') if isinstance(r['hora'], datetime) else str(r['hora'])

        resultados_serializables.append(r)

    return jsonify({"citas": resultados_serializables})

@app.route("/registrarReserva", methods=["POST"])
def registrar_reserva():
    data = request.get_json()

    required_fields = ["id_dueno", "id_producto", "id_tienda", "cantidad", "fecha_reserva", "fecha_finalizado", "total", "metodopago"]
    for field in required_fields:
        if field not in data or data[field] in (None, ""):
            return jsonify({"error": f"Falta el campo {field}"}), 400

    # Parsear fechas y convertir a string
    try:
        fecha_reserva_str = datetime.strptime(data["fecha_reserva"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
        fecha_finalizado_str = datetime.strptime(data["fecha_finalizado"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Use yyyy-MM-dd HH:mm:ss"}), 400

    # Convertir total a float
    try:
        total_float = float(data["total"])
    except Exception:
        return jsonify({"error": "Total inválido, debe ser un número"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    try:
        cursor = db.cursor()
        query = """
            INSERT INTO reserva (id_cliente, id_producto, id_tienda, cantidad, fecha_reserva, fecha_vencimiento, estado, total, tipo_pago)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (
            data["id_dueno"],
            data["id_producto"],
            data["id_tienda"],
            int(data["cantidad"]),
            fecha_reserva_str,  # enviar como string
            fecha_finalizado_str,  # enviar como string
            "Pendiente",
            total_float,  # enviar como float
            data["metodopago"]
        ))
        db.commit()
        cursor.close()
        db.close()

        return jsonify({"message": "Reserva registrada correctamente"}), 201

    except Exception as e:
        db.rollback()
        cursor.close()
        db.close()
        print("Error SQL:", e)  # <-- imprime el error real
        return jsonify({"error": str(e)}), 500
    
@app.route("/registrarPedido", methods=["POST"])
def registrar_pedido():
    data = request.get_json()

    required_fields = ["id_dueno", "id_tienda", "total", "metodopago", "fecha", "direccion"]
    for field in required_fields:
        if field not in data or data[field] in (None, ""):
            return jsonify({"error": f"Falta el campo {field}"}), 400

    # Parsear fechas y convertir a string
    try:
        fecha_reserva = datetime.strptime(data["fecha"], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Use yyyy-MM-dd HH:mm:ss"}), 400

    # Convertir total a float
    try:
        total_float = float(data["total"])
    except Exception:
        return jsonify({"error": "Total inválido, debe ser un número"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    try:
        cursor = db.cursor()
        query = """
            INSERT INTO pedido (id_cliente, id_tienda, direccion_envio, estado, metodo_pago, total, fecha)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (
            data["id_dueno"],
            data["id_tienda"],
            data["direccion"],
            "Pendiente",
            data["metodopago"],
            total_float, 
            fecha_reserva
        ))
        db.commit()
        id_pedido = cursor.lastrowid
        for prod in data["productos"]:
            query_producto = """
                INSERT INTO PedidoProducto (id_pedido, id_producto, cantidad)
                VALUES (%s, %s, %s)
            """
            cursor.execute(query_producto, (
                id_pedido,
                prod["idproducto"],
                prod["cantidadSeleccionada"]
            ))

        db.commit()
        cursor.close()
        db.close()

        return jsonify({"message": "Reserva registrada correctamente"}), 201

    except Exception as e:
        db.rollback()
        cursor.close()
        db.close()
        print("Error SQL:", e)  # <-- imprime el error real
        return jsonify({"error": str(e)}), 500

@app.route("/mispedidos", methods=["POST"])
def obtenerPedidos_usuario():
    data = request.get_json()
    id_dueno = data.get("id_dueno")

    if not id_dueno:
        return jsonify({"error": "Falta la cédula"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("""
    SELECT 
    p.idpedido,
    p.id_cliente,
    p.id_tienda,
    t.nombre_negocio,    
    p.total,
    p.metodo_pago,
    p.direccion_envio,
    p.fecha,
    p.estado,
    pp.id_producto,
    pp.cantidad,
    pr.nombre AS nombre_producto,
    pr.precio AS precio_producto,
    pr.imagen AS foto_producto
    FROM Pedido p
    JOIN Tienda t ON p.id_tienda = t.idtienda   
    JOIN PedidoProducto pp ON p.idpedido = pp.id_pedido
    JOIN Producto pr ON pp.id_producto = pr.idproducto
    WHERE p.id_cliente = %s;
    """, (id_dueno,))
    resultados = cursor.fetchall()
    cursor.close()
    db.close()

    resultados_serializables = []
    for r in resultados:
        # Convertir fecha y horas a string
        r['fecha'] = r['fecha'].strftime("%Y-%m-%d") if isinstance(r['fecha'], datetime) else str(r['fecha'])

        resultados_serializables.append(r)

    return jsonify({"pedido": resultados_serializables})

@app.route("/cancelar_pedido", methods=["PUT"])
def cancelar_pedido():
    data = request.get_json()
    id = data.get("id")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE pedido SET estado = %s WHERE idpedido = %s"
    cursor.execute(sql, ("Cancelado", id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Pedido cancelado correctamente"}), 200

@app.route("/recibido_pedido", methods=["PUT"])
def recibido_pedido():
    data = request.get_json()
    id = data.get("id")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE pedido SET estado = %s WHERE idpedido = %s"
    cursor.execute(sql, ("Recibido", id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Pedido recibido correctamente"}), 200

@app.route("/norecibido_pedido", methods=["PUT"])
def Norecibido_pedido():
    data = request.get_json()
    id = data.get("id")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE pedido SET estado = %s WHERE idpedido = %s"
    cursor.execute(sql, ("No recibido", id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Pedido recibido correctamente"}), 200

@app.route("/misreservas", methods=["POST"])
def obtenerReservas_usuario():
    data = request.get_json()
    id_dueno = data.get("id_dueno")

    if not id_dueno:
        return jsonify({"error": "Falta la cédula"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500
    
    cursor = db.cursor()
    cursor.execute("""
        UPDATE reserva
        SET estado = 'Vencida'
        WHERE estado = 'pendiente' AND fecha_vencimiento < NOW();
    """)
    db.commit()
    cursor.close()

    cursor = db.cursor(dictionary=True)
    cursor.execute("""
    SELECT 
    r.idreserva,
    r.id_tienda,
    t.nombre_negocio,
    r.id_producto,
    p.nombre AS nombre_producto,
    p.imagen AS imagen_producto,
    p.precio AS precio_producto,
    r.cantidad,
    r.fecha_reserva,
    r.fecha_vencimiento,
    r.estado,
    r.total,
    r.tipo_pago
    FROM reserva r
    JOIN producto p ON r.id_producto = p.idproducto
    JOIN tienda t ON r.id_tienda = t.idtienda
    WHERE r.id_cliente = %s;
    """, (id_dueno,))
    resultados = cursor.fetchall()
    cursor.close()
    db.close()

    resultados_serializables = []
    for r in resultados:
        # Convertir fecha y horas a string
        r['fecha_reserva'] = r['fecha_reserva'].strftime("%Y-%m-%d") if isinstance(r['fecha_reserva'], datetime) else str(r['fecha_reserva'])
        r['fecha_vencimiento'] = r['fecha_vencimiento'].strftime("%Y-%m-%d %H:%M:%S") if isinstance(r['fecha_vencimiento'], datetime) else str(r['fecha_vencimiento'])
        resultados_serializables.append(r)

    return jsonify({"reserva": resultados_serializables})

@app.route("/cancelar_reserva", methods=["PUT"])
def cancelar_reserva():
    data = request.get_json()
    id = data.get("id")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE reserva SET estado = %s WHERE idreserva = %s"
    cursor.execute(sql, ("Cancelada", id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Reserva cancelada correctamente"}), 200

@app.route("/reserva_completada", methods=["PUT"])
def completar_reserva():
    data = request.get_json()
    id = data.get("id")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE reserva SET estado = %s WHERE idreserva = %s"
    cursor.execute(sql, ("Recogida", id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Reserva completada correctamente"}), 200

@app.route("/pedidos", methods=["POST"])
def obtenerPedido():
    data = request.get_json()
    id_tienda = data.get("id_tienda")

    if not id_tienda:
        return jsonify({"error": "Falta la cédula"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor(dictionary=True)
    cursor.execute("""
    SELECT 
    p.idpedido,
    p.id_cliente,
    dm.nombre AS nombre_cliente,
    dm.apellido AS apellido_cliente,
    p.id_tienda,
    t.nombre_negocio,
    p.total,
    p.metodo_pago,
    p.direccion_envio,
    p.fecha,
    p.estado,
    pp.id_producto,
    pp.cantidad,
    pr.nombre AS nombre_producto,
    pr.precio AS precio_producto,
    pr.imagen AS foto_producto
    FROM Pedido p
    JOIN Tienda t ON p.id_tienda = t.idtienda
    JOIN PedidoProducto pp ON p.idpedido = pp.id_pedido
    JOIN Producto pr ON pp.id_producto = pr.idproducto
    LEFT JOIN dueno_mascotas dm ON p.id_cliente = dm.id_dueno
    WHERE p.id_tienda = %s;
    """, (id_tienda,))
    resultados = cursor.fetchall()
    cursor.close()
    db.close()

    resultados_serializables = []
    for r in resultados:
        # Convertir fecha y horas a string
        r['fecha'] = r['fecha'].strftime("%Y-%m-%d") if isinstance(r['fecha'], datetime) else str(r['fecha'])

        resultados_serializables.append(r)

    return jsonify({"pedido": resultados_serializables})

@app.route("/enviado_pedido", methods=["PUT"])
def enviado_pedido():
    data = request.get_json()
    id_pedido = data.get("id")
    productos = data.get("productos", [])

    if not id_pedido:
        return jsonify({"error": "Falta id del pedido"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()

    try:
        # 1️⃣ Cambiar estado del pedido
        sql_pedido = "UPDATE pedido SET estado = %s WHERE idpedido = %s"
        cursor.execute(sql_pedido, ("Enviado", id_pedido))

        # 2️⃣ Restar inventario por cada producto
        for item in productos:
            id_producto = item.get("id_producto")
            cantidad = item.get("cantidad")

            if id_producto and cantidad:
                sql_resta = """
                    UPDATE producto 
                    SET cantidad_disponible = cantidad_disponible - %s
                    WHERE idproducto = %s
                """
                cursor.execute(sql_resta, (cantidad, id_producto))

        db.commit()
        return jsonify({"mensaje": "Pedido enviado y stock actualizado"}), 200

    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        db.close()
        
@app.route("/reservas", methods=["POST"])
def obtenerReservas():
    data = request.get_json()
    id_tienda = data.get("id_tienda")

    if not id_tienda:
        return jsonify({"error": "Falta la cédula"}), 400

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500
    
    cursor = db.cursor()
    cursor.execute("""
        UPDATE reserva
        SET estado = 'Vencida'
        WHERE estado = 'pendiente' AND fecha_vencimiento < NOW();
    """)
    db.commit()
    cursor.close()

    cursor = db.cursor(dictionary=True)
    cursor.execute("""
    SELECT 
    r.idreserva,
    r.id_tienda,
    t.nombre_negocio,
    r.id_producto,
    p.nombre AS nombre_producto,
    p.imagen AS imagen_producto,
    p.precio AS precio_producto,
    r.cantidad,
    r.fecha_reserva,
    r.fecha_vencimiento,
    r.estado,
    r.total,
    r.tipo_pago,
    dm.nombre AS nombre_cliente,
    dm.apellido AS apellido_cliente
    FROM reserva r
    JOIN producto p ON r.id_producto = p.idproducto
    JOIN tienda t ON r.id_tienda = t.idtienda
    LEFT JOIN dueno_mascotas dm ON r.id_cliente = dm.id_dueno
    WHERE r.id_tienda = %s;
    """, (id_tienda,))
    resultados = cursor.fetchall()
    cursor.close()
    db.close()

    resultados_serializables = []
    for r in resultados:
        # Convertir fecha y horas a string
        r['fecha_reserva'] = r['fecha_reserva'].strftime("%Y-%m-%d") if isinstance(r['fecha_reserva'], datetime) else str(r['fecha_reserva'])
        r['fecha_vencimiento'] = r['fecha_vencimiento'].strftime("%Y-%m-%d %H:%M:%S") if isinstance(r['fecha_vencimiento'], datetime) else str(r['fecha_vencimiento'])
        resultados_serializables.append(r)

    return jsonify({"reserva": resultados_serializables})

@app.route("/reserva_aceptada", methods=["PUT"])
def aceptar_reserva():
    data = request.get_json()
    id = data.get("id")

    db = get_connection()
    if db is None:
        return jsonify({"error": "No hay conexión a la base de datos"}), 500

    cursor = db.cursor()
    sql = "UPDATE reserva SET estado = %s WHERE idreserva = %s"
    cursor.execute(sql, ("Aceptada", id))
    db.commit()
    cursor.close()
    db.close()

    return jsonify({"mensaje": "Reserva aceptada correctamente"}), 200

if __name__ == "__main__":
    print("Iniciando servidor Flask...")
    # Opcional: probar la conexión antes de iniciar
    conn = get_connection()
    if conn:
        print("Conexión exitosa a MySQL")
        conn.close()
    else:
        print("Fallo en la conexión a MySQL")
    

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    
