// Tribal v2 ast_extract test fixture: Go.
package sample

import (
	"encoding/json"
	"fmt"
	"os"
)

type User struct {
	ID   string
	Name string
}

type UserService struct {
	dbPath string
}

func NewUserService(p string) *UserService {
	return &UserService{dbPath: p}
}

func (s *UserService) GetUser(uid string) (*User, error) {
	data, err := os.ReadFile(s.dbPath)
	if err != nil {
		return nil, err
	}
	var users map[string]*User
	if err := json.Unmarshal(data, &users); err != nil {
		return nil, err
	}
	return users[uid], nil
}

func Main() {
	svc := NewUserService("/tmp/db.json")
	u, _ := svc.GetUser("alice")
	fmt.Println(u.Name)
}
