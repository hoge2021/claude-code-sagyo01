// Tribal v2 ast_extract test fixture: Java.
package sample;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

public class Sample {
    public static class User {
        public String id;
        public String name;
    }

    public static class UserService {
        private final Path dbPath;

        public UserService(String dbPath) {
            this.dbPath = Path.of(dbPath);
        }

        public User getUser(String uid) throws IOException {
            String raw = Files.readString(this.dbPath);
            return parseUser(raw, uid);
        }

        private User parseUser(String raw, String uid) {
            User u = new User();
            u.id = uid;
            u.name = "stub";
            return u;
        }
    }

    public static void main(String[] args) throws IOException {
        UserService svc = new UserService("/tmp/db.json");
        User u = svc.getUser("alice");
        System.out.println(u.name);
    }
}
