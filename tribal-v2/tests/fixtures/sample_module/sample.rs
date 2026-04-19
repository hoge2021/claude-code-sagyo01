// Tribal v2 ast_extract test fixture: Rust.
use std::collections::HashMap;
use std::fs;

pub struct User {
    pub id: String,
    pub name: String,
}

pub struct UserService {
    db_path: String,
}

impl UserService {
    pub fn new(db_path: String) -> Self {
        Self { db_path }
    }

    pub fn get_user(&self, uid: &str) -> Option<User> {
        let raw = fs::read_to_string(&self.db_path).ok()?;
        let users: HashMap<String, (String, String)> = serde_json::from_str(&raw).ok()?;
        users.get(uid).map(|(id, name)| User {
            id: id.clone(),
            name: name.clone(),
        })
    }
}

pub fn main_fn() {
    let svc = UserService::new("/tmp/db.json".to_string());
    if let Some(u) = svc.get_user("alice") {
        println!("{}", u.name);
    }
}
