// Tribal v2 ast_extract test fixture: TypeScript.
import { readFileSync } from "fs";
import * as path from "path";

interface User {
  id: string;
  name: string;
}

class UserService {
  private dbPath: string;

  constructor(dbPath: string) {
    this.dbPath = path.resolve(dbPath);
  }

  getUser(uid: string): User {
    const raw = readFileSync(this.dbPath, "utf-8");
    return JSON.parse(raw)[uid];
  }
}

function main(): void {
  const svc = new UserService("/tmp/db.json");
  const u = svc.getUser("alice");
  console.log(u.name);
}
