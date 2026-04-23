import tkinter as tk
import random

WINDOW_HEIGHT = 600  # ウィンドウの高さ
WINDOW_WIDTH = 600   # ウィンドウの幅

CANNON_Y = 550       # 自機のy座標

ENEMY_SPACE_X = 100  # 敵の間隔(x座標)
ENEMY_SPACE_Y = 40   # 敵の間隔(y座標)
ENEMY_MOVE_SPACE_X = 20  # 敵の移動間隔(x座標)
ENEMY_MOVE_SPEED = 500  # 敵の移動スピード(2000 ms)
NUMBER_OF_ENEMY = 10    # 敵の数
ENEMY_SHOOT_INTERVAL = 500  # 敵がランダムに弾を打ってくる間隔

COLLISION_DETECTION = 300  # 当たり判定

BULLET_HEIGHT = 10  # 弾の縦幅
BULLET_WIDTH = 2    # 弾の横幅
BULLET_SPEED = 10   # 弾のスピード(10 ms)

TEXT_GOOD_SIZE = 10             # goodのサイズ
TEXT_CONGRATULATIONS_SIZE = 50  # congratularionsのサイズ
TEXT_GAMECLEAR_SIZE = 60        # gameclearのサイズ
TEXT_GAMEOVER_SIZE = 90         # gameoverのサイズ


class Cannon:  # 自機

    def __init__(self, x, y=CANNON_Y):
        self.x = x
        self.y = y
        self.draw()
        self.bind()

    def draw(self):
        # 自機を逆向きの三角形で描画
        self.id = cv.create_polygon(
            self.x, self.y - 20, self.x + 15, self.y, self.x - 15, self.y, fill="blue", outline="black", tags="cannon")

    def bind(self):
        cv.tag_bind("cannon", "<ButtonPress-3>", self.pressed)
        cv.tag_bind("cannon", "<Button1-Motion>", self.dragged)

    def pressed(self, event):
        mybullet = MyBullet(event.x, self.y)
        mybullet.draw()
        mybullet.shoot()

    def dragged(self, event):
        coords = cv.coords(self.id)
        dx = event.x - coords[0]
        self.x += dx
        cv.coords(self.id, self.x, self.y - 20, self.x + 15, self.y, self.x - 15, self.y)
        
    def destroy(self):
        cv.delete(self.id)


class MyBullet:  # 自分の弾

    def __init__(self, x, y):
        self.x = x
        self.y = y

    def draw(self):
        self.id = cv.create_rectangle(
            self.x - BULLET_WIDTH, self.y + BULLET_HEIGHT, self.x + BULLET_WIDTH, self.y - BULLET_HEIGHT, fill="blue")

    def shoot(self):
        if self.y >= 0:
            cv.move(self.id, 0, -BULLET_HEIGHT)
            self.y -= BULLET_HEIGHT
            self.defeat()
            root.after(BULLET_SPEED, self.shoot)

    def defeat(self):
        for enemy in enemies:
            if enemy.exist and self.check_collision(enemy):
                enemy.exist = False
                enemy.destroy()
                cv.create_text(enemy.x, enemy.y, text="wow!", fill="cyan", font=(
                    "System", TEXT_GOOD_SIZE), tag="good")

    def check_collision(self, enemy):
        enemy_coords = cv.coords(enemy.id)
        bullet_coords = cv.coords(self.id)
        return (enemy_coords[0] < bullet_coords[0] < enemy_coords[2] and
                enemy_coords[1] < bullet_coords[1] < enemy_coords[3])

    def destroy(self):
        cv.delete(self.id)


class Enemy:  # 敵

    def __init__(self, x, y):
        self.x = x % WINDOW_WIDTH
        self.y = y + x // WINDOW_WIDTH * ENEMY_SPACE_Y
        self.exist = True
        self.draw()
        self.move()

    def draw(self):
        # 敵機を四角形で描画
        self.id = cv.create_rectangle(
            self.x - 15, self.y + 20, self.x + 15, self.y - 20, fill="red", outline="black", tags="enemy")

    def enemy_shoot(self):
        if self.exist:
            enemybullet = EnemyBullet(self.x, self.y)
            enemybullet.draw()
            enemybullet.shoot()

    def move(self):
        if self.exist:
            if self.x > WINDOW_WIDTH:
                self.x -= ENEMY_MOVE_SPACE_X
                self.y += ENEMY_SPACE_Y
            elif self.x < 0:
                self.x += ENEMY_MOVE_SPACE_X
                self.y += ENEMY_SPACE_Y
            if self.y % (ENEMY_SPACE_Y * 2) == ENEMY_SPACE_Y:
                self.x += ENEMY_MOVE_SPACE_X
            else:
                self.x -= ENEMY_MOVE_SPACE_X
            cv.coords(self.id, self.x - 15, self.y + 20, self.x + 15, self.y - 20)
            root.after(ENEMY_MOVE_SPEED, self.move)

    def destroy(self):
        cv.delete(self.id)


class EnemyBullet:  # 敵の弾

    def __init__(self, x, y):
        self.x = x
        self.y = y

    def draw(self):
        self.id = cv.create_rectangle(
            self.x - BULLET_WIDTH, self.y + BULLET_HEIGHT, self.x + BULLET_WIDTH, self.y - BULLET_HEIGHT, fill="red")

    def shoot(self):
        if self.y <= WINDOW_HEIGHT:
            cv.move(self.id, 0, BULLET_HEIGHT)
            self.y += BULLET_HEIGHT
            self.collision()
            root.after(BULLET_SPEED, self.shoot)

    def collision(self):
        if cannon.exist and self.check_collision():
            gameover()

    def check_collision(self):
        cannon_coords = cv.coords(cannon.id)
        bullet_coords = cv.coords(self.id)
        return (cannon_coords[0] < bullet_coords[0] < cannon_coords[2] and
                cannon_coords[1] < bullet_coords[1] < cannon_coords[3])

    def destroy(self):
        cv.delete(self.id)


def gameclear():
    winflag = 0
    for enemy in enemies:
        if enemy.exist == False:
            winflag += 1
    if winflag == NUMBER_OF_ENEMY:
        cv.create_text(WINDOW_WIDTH//2, WINDOW_HEIGHT//2 -
                       80, text="Congratulations!", fill="lime", font=("System", TEXT_CONGRATULATIONS_SIZE))
        cv.create_text(WINDOW_WIDTH//2, WINDOW_HEIGHT//2 +
                       20, text="GAME CLEAR!", fill="lime", font=("System", TEXT_GAMECLEAR_SIZE))
    root.after(1000, gameclear)


def gameover():
    if cannon.exist:
        cannon.exist = False
        cannon.destroy()
        cv.create_text(WINDOW_WIDTH//2, WINDOW_HEIGHT//2,
                       text="GAME OVER", fill="red", font=("System", TEXT_GAMEOVER_SIZE))


def enemy_randomshoot():
    enemy = random.choice(enemies)
    enemy.enemy_shoot()
    root.after(ENEMY_SHOOT_INTERVAL, enemy_randomshoot)


if __name__ == "__main__":
    root = tk.Tk()
    root.title("invader")
    cv = tk.Canvas(root, width=WINDOW_WIDTH,
                   height=WINDOW_HEIGHT, bg="yellowgreen")
    cv.pack()

    # 画像の読み込みは省略しています

    cannon = Cannon(WINDOW_WIDTH//2, CANNON_Y)
    cannon.exist = True  # プレイヤーの生存状態を表すフラグ
    enemies = []
    for i in range(NUMBER_OF_ENEMY):
        enemy_i = Enemy(i*ENEMY_SPACE_X+50, ENEMY_SPACE_Y)
        enemies.append(enemy_i)

    enemy_randomshoot()

    gameclear()

    root.mainloop()
