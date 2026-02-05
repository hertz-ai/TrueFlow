//! Example Actix-web application with TrueFlow instrumentation.
//!
//! Run with: TRUEFLOW_ENABLED=1 cargo run -p actix-example

use actix_web::{get, post, web, App, HttpResponse, HttpServer, Responder};
use serde::{Deserialize, Serialize};
use trueflow_macros::{trace, trace_impl};

#[derive(Debug, Serialize, Deserialize)]
struct User {
    id: u32,
    name: String,
    email: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct CreateUserRequest {
    name: String,
    email: String,
}

/// User service with TrueFlow instrumentation
struct UserService;

#[trace_impl]
impl UserService {
    fn new() -> Self {
        UserService
    }

    fn get_user(&self, id: u32) -> Option<User> {
        // Simulated database lookup
        self.validate_id(id)?;
        Some(User {
            id,
            name: format!("User {}", id),
            email: format!("user{}@example.com", id),
        })
    }

    fn create_user(&self, req: CreateUserRequest) -> User {
        // Simulated user creation
        let id = self.generate_id();
        self.save_to_database(&req);
        User {
            id,
            name: req.name,
            email: req.email,
        }
    }

    fn validate_id(&self, id: u32) -> Option<()> {
        if id > 0 && id < 1000 {
            Some(())
        } else {
            None
        }
    }

    fn generate_id(&self) -> u32 {
        // Simulated ID generation
        42
    }

    fn save_to_database(&self, _req: &CreateUserRequest) {
        // Simulated database save
        std::thread::sleep(std::time::Duration::from_millis(10));
    }
}

#[get("/")]
#[trace]
async fn index() -> impl Responder {
    HttpResponse::Ok().body("Welcome to TrueFlow Actix Example!")
}

#[get("/users/{id}")]
#[trace]
async fn get_user(path: web::Path<u32>) -> impl Responder {
    let id = path.into_inner();
    let service = UserService::new();

    match service.get_user(id) {
        Some(user) => HttpResponse::Ok().json(user),
        None => HttpResponse::NotFound().body("User not found"),
    }
}

#[post("/users")]
#[trace]
async fn create_user(body: web::Json<CreateUserRequest>) -> impl Responder {
    let service = UserService::new();
    let user = service.create_user(body.into_inner());
    HttpResponse::Created().json(user)
}

#[get("/health")]
async fn health_check() -> impl Responder {
    HttpResponse::Ok().body("OK")
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    // Initialize TrueFlow
    trueflow_runtime::init();

    println!("Starting server at http://127.0.0.1:8080");
    println!("TrueFlow tracing enabled on port 5681");

    HttpServer::new(|| {
        App::new()
            .service(index)
            .service(get_user)
            .service(create_user)
            .service(health_check)
    })
    .bind("127.0.0.1:8080")?
    .run()
    .await
}
