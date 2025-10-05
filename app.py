from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, Table
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from typing import List, Optional
from contextlib import asynccontextmanager
import os

# Configuración de la base de datos
DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:root_password@mysql:3306/cursos_db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Tabla intermedia para relación N-N curso-instructor
curso_instructor = Table(
    'curso_instructor', Base.metadata,
    Column('curso_id', Integer, ForeignKey('curso.id'), primary_key=True),
    Column('instructor_id', Integer, ForeignKey('instructor.id'), primary_key=True)
)

# Modelo Instructor
class Instructor(Base):
    __tablename__ = "instructor"
    
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(255), nullable=False)
    bio = Column(Text)
    foto_url = Column(String(500))
    
    # Relación N-N con cursos
    cursos = relationship("Curso", secondary=curso_instructor, back_populates="instructores")

# Modelo Curso
class Curso(Base):
    __tablename__ = "curso"
    
    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(255), unique=True, index=True, nullable=False)
    titulo = Column(String(255), nullable=False)
    descripcion = Column(Text)
    nivel = Column(String(50), nullable=False)
    estado = Column(String(50), nullable=False, default="borrador")
    duracion_min = Column(Integer, nullable=False, default=0)
    
    # Relaciones
    lecciones = relationship("Leccion", back_populates="curso", cascade="all, delete-orphan")
    instructores = relationship("Instructor", secondary=curso_instructor, back_populates="cursos")

# Modelo Leccion
class Leccion(Base):
    __tablename__ = "leccion"
    
    id = Column(Integer, primary_key=True, index=True)
    curso_id = Column(Integer, ForeignKey("curso.id"), nullable=False)
    titulo = Column(String(255), nullable=False)
    orden = Column(Integer, nullable=False)
    contenido_url = Column(String(500))
    duracion_min = Column(Integer, nullable=False, default=0)
    
    # Relación con curso
    curso = relationship("Curso", back_populates="lecciones")

# Modelos Pydantic para respuestas
class InstructorResponse(BaseModel):
    id: int
    nombre: str
    bio: Optional[str] = None
    foto_url: Optional[str] = None
    
    class Config:
        from_attributes = True

class CursoResponse(BaseModel):
    id: int
    slug: str
    titulo: str
    descripcion: Optional[str] = None
    nivel: str
    estado: str
    duracion_min: int
    instructores: List[InstructorResponse] = []
    
    class Config:
        from_attributes = True

class LeccionResponse(BaseModel):
    id: int
    curso_id: int
    titulo: str
    orden: int
    contenido_url: Optional[str] = None
    duracion_min: int

    class Config:
        from_attributes = True

# Modelos Pydantic para inputs de POST
class CreateInstructor(BaseModel):
    nombre: str
    bio: Optional[str] = None
    foto_url: Optional[str] = None

class CreateCurso(BaseModel):
    slug: str
    titulo: str
    descripcion: Optional[str] = None
    nivel: str
    estado: str = "borrador"
    duracion_min: int = 0
    instructor_ids: List[int] = []

class CreateLeccion(BaseModel):
    titulo: str
    orden: int
    contenido_url: Optional[str] = None
    duracion_min: int = 0

# Lifespan para crear tablas y datos al iniciar
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    import time
    max_retries = 5
    for attempt in range(max_retries):
        try:
            Base.metadata.create_all(bind=engine)
            print("✅ Tablas creadas exitosamente")
            

            
            break
        except Exception as e:
            print(f"❌ Intento {attempt + 1} falló: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                print("❌ No se pudieron crear las tablas después de 5 intentos")
    yield
    # Shutdown (si necesitas limpiar algo)

# Crear la aplicación FastAPI
app = FastAPI(title="MS Cursos API", description="Microservicio de Cursos con MySQL", version="1.0.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency para obtener la sesión de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Endpoints

@app.post("/instructores", response_model=InstructorResponse)
def create_instructor(instructor: CreateInstructor, db: Session = Depends(get_db)):
    """POST /instructores - Crear un nuevo instructor"""
    db_instructor = Instructor(
        nombre=instructor.nombre,
        bio=instructor.bio,
        foto_url=instructor.foto_url
    )
    db.add(db_instructor)
    db.commit()
    db.refresh(db_instructor)
    return db_instructor

@app.post("/cursos", response_model=CursoResponse)
def create_curso(curso: CreateCurso, db: Session = Depends(get_db)):
    """POST /cursos - Crear un nuevo curso"""
    db_curso = Curso(
        slug=curso.slug,
        titulo=curso.titulo,
        descripcion=curso.descripcion,
        nivel=curso.nivel,
        estado=curso.estado,
        duracion_min=curso.duracion_min
    )
    # Asociar instructores si existen
    if curso.instructor_ids:
        instructores = db.query(Instructor).filter(Instructor.id.in_(curso.instructor_ids)).all()
        db_curso.instructores.extend(instructores)
    
    db.add(db_curso)
    db.commit()
    db.refresh(db_curso)
    return db_curso

@app.post("/cursos/{curso_id}/lecciones", response_model=LeccionResponse)
def create_leccion(curso_id: int, leccion: CreateLeccion, db: Session = Depends(get_db)):
    """POST /cursos/{curso_id}/lecciones - Crear una nueva lección para un curso"""
    curso = db.query(Curso).filter(Curso.id == curso_id).first()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    db_leccion = Leccion(
        curso_id=curso_id,
        titulo=leccion.titulo,
        orden=leccion.orden,
        contenido_url=leccion.contenido_url,
        duracion_min=leccion.duracion_min
    )
    db.add(db_leccion)
    db.commit()
    db.refresh(db_leccion)
    return db_leccion

@app.get("/cursos/{curso_id}", response_model=CursoResponse)
def get_curso(curso_id: int, db: Session = Depends(get_db)):
    """GET /cursos/{id} - Retorna información general del curso"""
    curso = db.query(Curso).filter(Curso.id == curso_id).first()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    # Cargar instructores
    db.refresh(curso)
    return curso

@app.get("/cursos/{curso_id}/lecciones", response_model=List[LeccionResponse])
def get_lecciones_curso(curso_id: int, db: Session = Depends(get_db)):
    """GET /cursos/{id}/lecciones - Retorna lecciones del curso ordenadas"""
    curso = db.query(Curso).filter(Curso.id == curso_id).first()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    lecciones = db.query(Leccion).filter(Leccion.curso_id == curso_id).order_by(Leccion.orden).all()
    return lecciones

@app.get("/cursos", response_model=List[CursoResponse])
def get_cursos(
    estado: Optional[str] = Query(None, description="Filtrar por estado"),
    nivel: Optional[str] = Query(None, description="Filtrar por nivel"),
    page: int = Query(1, ge=1, description="Número de página"),
    size: int = Query(10, ge=1, le=100, description="Tamaño de página"),
    db: Session = Depends(get_db)
):
    """GET /cursos?estado=publicado - Lista filtrada y paginada de cursos"""
    query = db.query(Curso)

    if estado:
        query = query.filter(Curso.estado == estado)
    if nivel:
        query = query.filter(Curso.nivel == nivel)

    offset = (page - 1) * size
    cursos = query.offset(offset).limit(size).all()

    # Cargar instructores para cada curso
    for curso in cursos:
        db.refresh(curso)

    return cursos

@app.delete("/instructores/{instructor_id}", status_code=204)
def delete_instructor(instructor_id: int, db: Session = Depends(get_db)):
    """DELETE /instructores/{instructor_id} - Eliminar un instructor"""
    instructor = db.query(Instructor).filter(Instructor.id == instructor_id).first()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor no encontrado")
    db.delete(instructor)
    db.commit()
    return

@app.patch("/instructores/{instructor_id}", response_model=InstructorResponse)
def update_instructor(instructor_id: int, instructor_data: CreateInstructor, db: Session = Depends(get_db)):
    """PATCH /instructores/{instructor_id} - Actualizar un instructor"""
    instructor = db.query(Instructor).filter(Instructor.id == instructor_id).first()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor no encontrado")
    for key, value in instructor_data.dict(exclude_unset=True).items():
        setattr(instructor, key, value)
    db.commit()
    db.refresh(instructor)
    return instructor

@app.delete("/cursos/{curso_id}", status_code=204)
def delete_curso(curso_id: int, db: Session = Depends(get_db)):
    """DELETE /cursos/{curso_id} - Eliminar un curso"""
    curso = db.query(Curso).filter(Curso.id == curso_id).first()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    db.delete(curso)
    db.commit()
    return

@app.patch("/cursos/{curso_id}", response_model=CursoResponse)
def update_curso(curso_id: int, curso_data: CreateCurso, db: Session = Depends(get_db)):
    """PATCH /cursos/{curso_id} - Actualizar un curso"""
    curso = db.query(Curso).filter(Curso.id == curso_id).first()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")
    for key, value in curso_data.dict(exclude_unset=True).items():
        if key == "instructor_ids":
            instructores = db.query(Instructor).filter(Instructor.id.in_(value)).all()
            curso.instructores = instructores
        else:
            setattr(curso, key, value)
    db.commit()
    db.refresh(curso)
    return curso

@app.delete("/cursos/{curso_id}/lecciones/{leccion_id}", status_code=204)
def delete_leccion(curso_id: int, leccion_id: int, db: Session = Depends(get_db)):
    """DELETE /cursos/{curso_id}/lecciones/{leccion_id} - Eliminar una lección"""
    leccion = db.query(Leccion).filter(Leccion.id == leccion_id, Leccion.curso_id == curso_id).first()
    if not leccion:
        raise HTTPException(status_code=404, detail="Lección no encontrada")
    db.delete(leccion)
    db.commit()
    return

@app.patch("/cursos/{curso_id}/lecciones/{leccion_id}", response_model=LeccionResponse)
def update_leccion(curso_id: int, leccion_id: int, leccion_data: CreateLeccion, db: Session = Depends(get_db)):
    """PATCH /cursos/{curso_id}/lecciones/{leccion_id} - Actualizar una lección"""
    leccion = db.query(Leccion).filter(Leccion.id == leccion_id, Leccion.curso_id == curso_id).first()
    if not leccion:
        raise HTTPException(status_code=404, detail="Lección no encontrada")
    for key, value in leccion_data.dict(exclude_unset=True).items():
        setattr(leccion, key, value)
    db.commit()
    db.refresh(leccion)
    return leccion

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "ms-cursos", "port": 8010}


def init_sample_data():
    """Inicializar datos de ejemplo automáticamente"""
    db = SessionLocal()
    
    try:
        # Verificar si ya hay datos
        if db.query(Curso).count() > 0:
            print("✅ La base de datos ya tiene datos")
            return
        
        # Crear instructores
        instructor1 = Instructor(
            nombre="María López",
            bio="Experta en Cloud Computing con más de 10 años de experiencia",
            foto_url="https://example.com/maria.jpg"
        )
        
        instructor2 = Instructor(
            nombre="Carlos Rodríguez",
            bio="Especialista en DevOps y automatización",
            foto_url="https://example.com/carlos.jpg"
        )
        
        db.add(instructor1)
        db.add(instructor2)
        db.commit()
        
        # Crear cursos
        curso1 = Curso(
            slug="cloud-computing-101",
            titulo="Cloud Computing 101",
            descripcion="Fundamentos de AWS, Azure y Google Cloud Platform",
            nivel="beginner",
            estado="publicado",
            duracion_min=240
        )
        
        curso2 = Curso(
            slug="devops-avanzado",
            titulo="DevOps Avanzado",
            descripcion="Técnicas avanzadas de DevOps y CI/CD",
            nivel="advanced",
            estado="publicado",
            duracion_min=180
        )
        
        curso3 = Curso(
            slug="microservicios-python",
            titulo="Microservicios con Python",
            descripcion="Desarrollo de microservicios usando FastAPI",
            nivel="intermediate",
            estado="borrador",
            duracion_min=300
        )
        
        db.add(curso1)
        db.add(curso2)
        db.add(curso3)
        db.commit()
        
        # Asociar instructores con cursos
        curso1.instructores.append(instructor1)
        curso2.instructores.append(instructor2)
        curso3.instructores.extend([instructor1, instructor2])
        
        db.commit()
        
        # Crear lecciones
        lecciones_curso1 = [
            Leccion(curso_id=curso1.id, titulo="Introducción a Cloud Computing", orden=1, contenido_url="https://example.com/leccion1", duracion_min=30),
            Leccion(curso_id=curso1.id, titulo="AWS Fundamentals", orden=2, contenido_url="https://example.com/leccion2", duracion_min=45),
            Leccion(curso_id=curso1.id, titulo="Azure Basics", orden=3, contenido_url="https://example.com/leccion3", duracion_min=40),
            Leccion(curso_id=curso1.id, titulo="Google Cloud Platform", orden=4, contenido_url="https://example.com/leccion4", duracion_min=35),
        ]
        
        lecciones_curso2 = [
            Leccion(curso_id=curso2.id, titulo="Introducción a DevOps", orden=1, contenido_url="https://example.com/devops1", duracion_min=25),
            Leccion(curso_id=curso2.id, titulo="CI/CD Pipelines", orden=2, contenido_url="https://example.com/devops2", duracion_min=50),
            Leccion(curso_id=curso2.id, titulo="Containerización", orden=3, contenido_url="https://example.com/devops3", duracion_min=40),
        ]
        
        lecciones_curso3 = [
            Leccion(curso_id=curso3.id, titulo="FastAPI Basics", orden=1, contenido_url="https://example.com/fastapi1", duracion_min=60),
            Leccion(curso_id=curso3.id, titulo="Database Integration", orden=2, contenido_url="https://example.com/fastapi2", duracion_min=45),
        ]
        
        for leccion in lecciones_curso1 + lecciones_curso2 + lecciones_curso3:
            db.add(leccion)
        
        db.commit()
        
        print("✅ Base de datos inicializada con datos de ejemplo")
        print(f"   - {db.query(Instructor).count()} instructores creados")
        print(f"   - {db.query(Curso).count()} cursos creados")
        print(f"   - {db.query(Leccion).count()} lecciones creadas")
        
    except Exception as e:
        print(f"❌ Error inicializando base de datos: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)
