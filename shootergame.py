"""
========================================
  micro:bit シューター
  操作:
    micro:bit 傾ける    → 自機移動
    micro:bit Aボタン   → 弾を発射
    micro:bit Bボタン   → ボム（全敵破壊）
  ※ micro:bitが繋がっていない場合はキーボードで操作:
    矢印キー → 移動
    Z / Space → 射撃
    X        → ボム
========================================
"""

import pygame
import sys
import random
import threading
import math
from pathlib import Path

# pyserial がなければキーボードモードへ
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("[警告] pyserialがインストールされていません。")
    print("  pip install pyserial  でインストールしてください。")
    print("  キーボードモードで起動します。\n")

# ============================================================
# 定数
# ============================================================
WIDTH, HEIGHT = 1920, 1080
FPS = 60

BLACK = (135, 206, 235)
WHITE   = (255, 255, 255)
CYAN    = (0,   220, 255)
RED     = (255,  50,  50)
ORANGE  = (255, 160,   0)
YELLOW  = (255, 230,   0)
GREEN   = (0,   255, 120)
PURPLE  = (200,   0, 255)
GRAY    = (120, 120, 140)
DARK_RED= (180,  20,  20)

# ============================================================
# シリアル通信（別スレッド）
# ============================================================
controller_data = {'x': 0, 'y': 0, 'a': 0, 'b': 0, 's': 0}
serial_lock = threading.Lock()
use_keyboard = False

# キャリブレーション用オフセット（平置き時の値を引く）
calib_offset = {'x': 0, 'y': 0}
calib_done = False


def find_microbit_port():
    """micro:bitのシリアルポートを自動検出"""
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = p.description.lower()
        if any(k in desc for k in ['mbed', 'microbit', 'micro:bit', 'kl26']):
            return p.device
    # 見つからなければ最初のポートを試す
    if ports:
        print(f"[情報] micro:bitが特定できないため {ports[0].device} を使用します")
        return ports[0].device
    return None


def serial_reader(ser):
    """シリアルポートを読み続けるスレッド関数"""
    global calib_done, calib_offset
    calib_samples = []
    while True:
        try:
            raw = ser.readline()
            line = raw.decode('utf-8', errors='ignore').strip()
            parts = {}
            for item in line.split(','):
                if ':' in item:
                    k, v = item.split(':', 1)
                    parts[k.strip().lower()] = int(v.strip())
            if parts:
                if not calib_done:
                    calib_samples.append({'x': parts.get('x', 0), 'y': parts.get('y', 0)})
                    if len(calib_samples) >= 20:
                        calib_offset['x'] = sum(s['x'] for s in calib_samples) // 20
                        calib_offset['y'] = sum(s['y'] for s in calib_samples) // 20
                        calib_done = True
                        print(f"[キャリブレーション完了] X={calib_offset['x']} Y={calib_offset['y']}")
                else:
                    parts['x'] = parts.get('x', 0) - calib_offset['x']
                    parts['y'] = parts.get('y', 0) - calib_offset['y']
                    with serial_lock:
                        controller_data.update(parts)
        except Exception:
            pass


# ============================================================
# ゲームオブジェクト
# ============================================================

class Star:
    """背景の星"""
    def __init__(self):
        self.reset(initial=True)

    def reset(self, initial=False):
        self.x = random.uniform(0, WIDTH)
        self.y = random.uniform(0, HEIGHT) if initial else 0
        self.speed = random.uniform(1.0, 4.0)
        self.r = random.randint(1, 2)
        b = random.randint(80, 220)
        self.color = (b, b, min(255, b + 40))

    def update(self):
        self.y += self.speed
        if self.y > HEIGHT:
            self.reset()

    def draw(self, screen):
        pygame.draw.circle(screen, self.color, (int(self.x), int(self.y)), self.r)


class Bullet(pygame.sprite.Sprite):
    """プレイヤーの弾 ── 明るいシアン＋白コア（視認性UP）"""
    def __init__(self, x, y):
        super().__init__()
        W, H = 10, 28
        self.image = pygame.Surface((W, H), pygame.SRCALPHA)
        # 外側：シアンのグロー（先端ほど濃い）
        for i in range(H):
            t = i / H           # 0=先端, 1=末端
            alpha = int(200 * (1 - t))
            pygame.draw.line(self.image, (0, 220, 255, alpha), (0, i), (W - 1, i))
        # 中央：白いコア（細く明るく）
        for i in range(H):
            t = i / H
            alpha = int(255 * (1 - t))
            pygame.draw.line(self.image, (255, 255, 255, alpha),
                             (W // 2 - 1, i), (W // 2 + 1, i))
        self.rect = self.image.get_rect(centerx=x, bottom=y)
        self.speed = -14

    def update(self):
        self.rect.y += self.speed
        if self.rect.bottom < 0:
            self.kill()


class EnemyBullet(pygame.sprite.Sprite):
    """敵の弾 ── マゼンタ＋白コアで自機弾と明確に区別"""
    def __init__(self, x, y, dx=0, dy=3):
        super().__init__()
        SIZE = 18          # 旧14 → 18 でやや大きく
        self.image = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
        cx = cy = SIZE // 2
        # 外周：明るいマゼンタ（ピンク寄り）
        pygame.draw.circle(self.image, (255, 50, 220),  (cx, cy), cx)
        # 中間：濃いマゼンタリング
        pygame.draw.circle(self.image, (200,  0, 180),  (cx, cy), cx - 3)
        # コア：白（一目で「弾！」とわかる）
        pygame.draw.circle(self.image, (255, 255, 255), (cx, cy), 4)
        self.rect = self.image.get_rect(centerx=x, top=y)
        self.dx = dx
        self.dy = dy

    def update(self):
        self.rect.x += self.dx
        self.rect.y += self.dy
        if self.rect.top > HEIGHT or self.rect.left < 0 or self.rect.right > WIDTH:
            self.kill()


class Player(pygame.sprite.Sprite):
    """自機"""
    SHOOT_COOLDOWN = 8   # フレーム
    BOMB_COOLDOWN  = 300  # フレーム (5秒)
    INVINCIBLE_FRAMES = 250

    def __init__(self):
        super().__init__()
        self.base_image = self._make_image()
        self.image = self.base_image.copy()
        self.rect = self.image.get_rect(center=(WIDTH // 2, 750))
        self.shoot_cd = 0
        self.bomb_cd = self.BOMB_COOLDOWN
        self.invincible = 0
        self.lives = 5
        self.score = 0
        self.speed = 6
        self.power = 0
        self.max_power = 5

    def _make_image(self):
        img = pygame.image.load('images/player2.png').convert_alpha()
        img = pygame.transform.smoothscale(img, (200, 200))
        return img

    def update(self, controller, keys):
        if use_keyboard:
            dx = (keys[pygame.K_RIGHT] - keys[pygame.K_LEFT]) * self.speed
            dy = (keys[pygame.K_DOWN]  - keys[pygame.K_UP])   * self.speed
        else:
            with serial_lock:
                ax = controller['x']
                ay = controller['y']
            DEAD_ZONE = 80
            dx = 0 if abs(ax) < DEAD_ZONE else int(ax / 1024 * self.speed * 2.5)
            dy = 0 if abs(ay) < DEAD_ZONE else int(ay / 1024 * self.speed * 2.5)

        self.rect.x = max(0, min(WIDTH  - self.rect.width,  self.rect.x + dx))
        self.rect.y = max(0, min(HEIGHT - self.rect.height, self.rect.y + dy))

        if self.shoot_cd > 0:
            self.shoot_cd -= 1
        if self.bomb_cd > 0:
            self.bomb_cd -= 1
        if self.invincible > 0:
            self.invincible -= 1

        # 無敵中は点滅
        if self.invincible > 0 and (self.invincible // 6) % 2 == 0:
            self.image = pygame.Surface((200, 200), pygame.SRCALPHA)  # 透明
        else:
            self.image = self.base_image.copy()

    def try_shoot(self):
        """射撃を試みる。成功したらBulletインスタンスを返す"""
        if self.shoot_cd == 0:
            self.shoot_cd = self.SHOOT_COOLDOWN
            return Bullet(self.rect.centerx, self.rect.top)
        return None

    def try_bomb(self):
        """ボムを試みる。クールダウン中でなければTrueを返す"""
        if self.bomb_cd == 0:
            self.bomb_cd = self.BOMB_COOLDOWN
            return True
        return False

    def hit(self):
        """ダメージを受ける。無敵中でなければTrueを返す"""
        if self.invincible == 0:
            self.lives -= 1
            self.invincible = self.INVINCIBLE_FRAMES
            return True
        return False


class Enemy(pygame.sprite.Sprite):
    SHOOT_INTERVAL = {
        'normal': 90,
        'fast': 50,
        'tank': 120,
    }

    HP_TABLE = {
        'normal': 1,
        'fast': 1,
        'tank': 4,
    }

    SCORE_TABLE = {
    'normal': 200,
    'fast': 300,
    'tank': 500,
    }

    def __init__(self, etype):
        super().__init__()
        self.etype = etype

        self.base_image = self._make_image()
        self.image = self.base_image.copy()

        margin = self.base_image.get_width() // 2
        x = random.randint(margin, WIDTH - margin)
        self.rect = self.image.get_rect(center=(x, 0))
        self.rect.y = -self.rect.height + 20

        self.max_hp = self.HP_TABLE[self.etype]
        self.hp = self.max_hp
        self.score_val = self.SCORE_TABLE[self.etype]

        self._set_speed()
        self.shoot_timer = random.randint(20, self.SHOOT_INTERVAL[self.etype])

        self.radius = min(self.rect.width, self.rect.height) // 2

    def _make_image(self):
        img = pygame.image.load('images/enemy.png').convert_alpha()

        if self.etype == 'normal':
            size = (250, 250)
        elif self.etype == 'fast':
            size = (60, 60)
        else:  # tank
            size = (150, 150)

        img = pygame.transform.smoothscale(img, size)
        return img

    def _set_speed(self):
        if self.etype == 'normal':
            self.vx = random.uniform(-1.2, 1.2)
            self.vy = random.uniform(1.8, 3.5)
        elif self.etype == 'fast':
            self.vx = random.uniform(-2.5, 2.5)
            self.vy = random.uniform(4.0, 7.0)
        elif self.etype == 'tank':
            self.vx = random.uniform(-0.5, 0.5)
            self.vy = random.uniform(0.8, 1.5)

    def update(self):
        self.rect.x += self.vx
        self.rect.y += self.vy

        if self.rect.left < 0 or self.rect.right > WIDTH:
            self.vx *= -1

        if self.rect.top > HEIGHT:
            self.kill()

        if self.shoot_timer > 0:
            self.shoot_timer -= 1

    def can_shoot(self):
        if self.shoot_timer <= 0:
            self.shoot_timer = self.SHOOT_INTERVAL[self.etype] + random.randint(-20, 20)
            return True
        return False

    def take_hit(self):
        self.hp -= 1
        return self.hp <= 0

    def draw_hp_bar(self, screen):
        if self.etype == 'tank' and self.hp < self.max_hp:
            bw = self.rect.width
            ratio = self.hp / self.max_hp
            pygame.draw.rect(screen, GRAY, (self.rect.left, self.rect.top - 8, bw, 5))
            pygame.draw.rect(screen, GREEN, (self.rect.left, self.rect.top - 8, int(bw * ratio), 5))

class Explosion(pygame.sprite.Sprite):
    """爆発エフェクト"""
    def __init__(self, center, size=40):
        super().__init__()
        self.frames = self._gen_frames(size)
        self.idx = 0
        self.image = self.frames[0]
        self.rect = self.image.get_rect(center=center)
        self._timer = 0

    def _gen_frames(self, size):
        frames = []
        n = 10
        for i in range(n):
            s = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            t = i / (n - 1)
            r = int(size * (0.3 + 0.7 * t))
            a = int(255 * (1 - t))
            # 外炎
            c1 = (255, int(180 * (1 - t)), 0, a)
            pygame.draw.circle(s, c1, (size, size), r)
            # 内炎
            r2 = max(1, int(r * 0.5))
            c2 = (255, 240, 200, min(255, a + 80))
            pygame.draw.circle(s, c2, (size, size), r2)
            frames.append(s)
        return frames

    def update(self):
        self._timer += 1
        if self._timer % 3 == 0:
            self.idx += 1
            if self.idx >= len(self.frames):
                self.kill()
                return
            self.image = self.frames[self.idx]


class BombEffect(pygame.sprite.Sprite):
    """ボム爆発エフェクト（画面全体）"""
    def __init__(self):
        super().__init__()
        self.image = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.rect = self.image.get_rect()
        self.life = 20

    def update(self):
        self.life -= 1
        alpha = int(200 * self.life / 20)
        self.image.fill((255, 255, 255, alpha))
        if self.life <= 0:
            self.kill()


# ============================================================
# HUD 描画
# ============================================================

def draw_hud(screen, player, font, small_font, time_font, level, remaining_sec):
    sw = screen.get_width()
    sh = screen.get_height()

    # スコア（中央上）
    sc = font.render(f"SCORE  {player.score:06d}", True, WHITE)
    screen.blit(sc, (sw // 2 - sc.get_width() // 2, 8))

    # 残り時間（右上・大きく）
    timer_color = RED if remaining_sec <= 10 else WHITE
    tm = time_font.render(f"TIME {remaining_sec}", True, timer_color)
    screen.blit(tm, (sw - tm.get_width() - 20, 10))

    # ライフ（左上）
    for i in range(player.lives):
        pts = [
            (16 + i * 28, 12),
            (28 + i * 28, 32),
            (16 + i * 28, 26),
            (4 + i * 28, 32),
        ]
        pygame.draw.polygon(screen, CYAN, pts)
        pygame.draw.polygon(screen, WHITE, pts, 1)

    # レベル（右上、TIMEの下）
    lv = font.render(f"LV {level}", True, YELLOW)
    screen.blit(lv, (sw - lv.get_width() - 20, 62))

    # ボムゲージ（左下）
    bomb_ready = player.bomb_cd == 0
    bomb_color = GREEN if bomb_ready else GRAY
    bomb_label = "BOMB READY!" if bomb_ready else f"BOMB {player.bomb_cd // FPS + 1}s"
    bm = small_font.render(f"[B] {bomb_label}", True, bomb_color)
    screen.blit(bm, (12, sh - 28))

    if use_keyboard:
        hint = small_font.render("KB mode: Arrow=Move  Z=Shot  X=Bomb", True, GRAY)
        screen.blit(hint, (sw // 2 - hint.get_width() // 2, sh - 28))
        pw_text = small_font.render(
            f"POWER {player.power}/{player.max_power}",
            True,
            CYAN if player.power < player.max_power else YELLOW
        )
        screen.blit(pw_text, (12, sh - 55))

def draw_game_over(screen, font, big_font, score, title_text="GAME  OVER"):
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (0, 0))

    go = big_font.render(title_text, True, RED)
    sc = font.render(f"SCORE :  {score:06d}", True, WHITE)
    rs = font.render("[ R ]  Restart     [ ESC ]  Quit", True, YELLOW)

    screen.blit(go, (WIDTH // 2 - go.get_width() // 2, HEIGHT // 2 - 70))
    screen.blit(sc, (WIDTH // 2 - sc.get_width() // 2, HEIGHT // 2 + 10))
    screen.blit(rs, (WIDTH // 2 - rs.get_width() // 2, HEIGHT // 2 + 60))


class SpecialBullet(pygame.sprite.Sprite):
    def __init__(self, x, y, dx, dy):
        super().__init__()
        self.image = pygame.Surface((18, 18), pygame.SRCALPHA)
        pygame.draw.circle(self.image, CYAN, (9, 9), 9)
        pygame.draw.circle(self.image, WHITE, (9, 9), 5)
        self.rect = self.image.get_rect(center=(x, y))
        self.dx = dx
        self.dy = dy

    def update(self):
        self.rect.x += self.dx
        self.rect.y += self.dy
        if (
            self.rect.right < 0 or self.rect.left > WIDTH or
            self.rect.bottom < 0 or self.rect.top > HEIGHT
        ):
            self.kill()

# ============================================================
# メインループ
# ============================================================

def run_game(serial_port=None):
    global use_keyboard
    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.init()
        # --- BGM読み込み ---
    current_dir = Path(__file__).resolve().parent
    bgm_path = current_dir / "bgm" / "bgm.mp3"

    try:
        pygame.mixer.music.load(str(bgm_path))
        pygame.mixer.music.set_volume(0.5)   # 0.0〜1.0
        pygame.mixer.music.play(-1)          # -1でループ
    except Exception as e:
        print(f"[警告] BGMを読み込めませんでした: {e}")

    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("micro:bit シューター")
    clock = pygame.time.Clock()


    font = pygame.font.SysFont('Arial', 22, bold=True)
    big_font = pygame.font.SysFont('Arial', 54, bold=True)
    small_font = pygame.font.SysFont('Arial', 30)
    time_font = pygame.font.SysFont('Arial', 48, bold=True)

    # シリアル接続試行
    ser = None
    if SERIAL_AVAILABLE:
        port = serial_port or find_microbit_port()
        if port:
            try:
                ser = serial.Serial(port, 115200, timeout=0.1)
                t = threading.Thread(target=serial_reader, args=(ser,), daemon=True)
                t.start()
                print(f"[OK] micro:bit 接続: {port}")
                use_keyboard = False
            except Exception as e:
                print(f"[警告] シリアル接続失敗: {e}  → キーボードモードで起動します")
                use_keyboard = True
        else:
            print("[情報] micro:bitが見つかりません  → キーボードモードで起動します")
            use_keyboard = True
    else:
        use_keyboard = True

    # --- スプライトグループ ---
    all_sprites   = pygame.sprite.Group()
    bullets       = pygame.sprite.Group()
    enemies       = pygame.sprite.Group()
    enemy_bullets = pygame.sprite.Group()
    effects       = pygame.sprite.Group()

    player = Player()
    all_sprites.add(player)

    stars = [Star() for _ in range(90)]

    # ゲーム状態
    level = 1
    spawn_timer    = 0
    spawn_interval = 80   # フレームごとに敵を1体スポーン
    game_over = False
    prev_b = 0
    prev_s = 0
    time_limit_sec = 60
    start_ticks = pygame.time.get_ticks()
    time_up = False

    running = True
    while running:

        clock.tick(FPS)

        # ---------- イベント ----------
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                if game_over and event.key == pygame.K_r:
                    if ser:
                        ser.close()
                    pygame.quit()
                    run_game(serial_port)
                    return
                # キーボードボム
                if not game_over and event.key == pygame.K_x:
                    if player.try_bomb():
                        _do_bomb(player, enemies, effects, all_sprites)

        if game_over:
            screen.fill(BLACK)
            for s in stars:
                s.update()
                s.draw(screen)

            title = "TIME  UP" if time_up else "GAME  OVER"
            draw_game_over(screen, font, big_font, player.score, title)

            pygame.display.flip()
            continue

        # ---------- 入力 ----------
        keys = pygame.key.get_pressed()

        with serial_lock:
            cur_a = controller_data['a']
            cur_b = controller_data['b']
            cur_s = controller_data['s']

        # Aボタン / Z / Space → 射撃
        if cur_a or keys[pygame.K_z] or keys[pygame.K_SPACE]:
            b = player.try_shoot()
            if b:
                bullets.add(b)
                all_sprites.add(b)

        # Bボタン（立ち上がりエッジ）→ ボム
        if cur_b == 1 and prev_b == 0:
            if player.try_bomb():
                _do_bomb(player, enemies, effects, all_sprites)
        prev_b = cur_b

        if cur_s == 1 and prev_s == 0 and player.power >= player.max_power:
            _do_special_attack(player, bullets, all_sprites)
            player.power = 0

        prev_s = cur_s
        elapsed_sec = (pygame.time.get_ticks() - start_ticks) // 1000
        remaining_sec = max(0, time_limit_sec - elapsed_sec)
        if remaining_sec <= 0:
            time_up = True
            game_over = True
        if remaining_sec <= 10:
            current_spawn_interval = max(18, spawn_interval - 10)
        else:
            current_spawn_interval = spawn_interval

        # ---------- 更新 ----------
        player.update(controller_data, keys)
        bullets.update()
        enemies.update()
        enemy_bullets.update()
        effects.update()
        for s in stars:
            s.update()

        # 敵スポーン（レベルに応じて間隔を短縮）
        spawn_timer += 1
        if spawn_timer >= current_spawn_interval:
            spawn_timer = 0
            etype = random.choices(
                ['normal', 'fast', 'tank'],
                weights=[60, 30, max(0, level * 3)]
            )[0]
            e = Enemy(etype)
            enemies.add(e)
            all_sprites.add(e)

        # レベルアップ
        new_level = 1 + player.score // 500
        if new_level > level:
            level = new_level
            spawn_interval = max(25, 80 - level * 5)

        # 敵の射撃
        for enemy in list(enemies):
            # 敵の射撃
            for enemy in list(enemies):
                if enemy.can_shoot():
                    eb = EnemyBullet(enemy.rect.centerx, enemy.rect.bottom, dy=3)
                    enemy_bullets.add(eb)
                    all_sprites.add(eb)

        # ---------- 衝突判定 ----------
        # 自弾 vs 敵
        hit_dict = pygame.sprite.groupcollide(enemies, bullets, False, True)
        for enemy, _ in hit_dict.items():
            if enemy.take_hit():
                player.score += enemy.score_val

                if enemy.etype == 'normal':
                    player.power = min(player.max_power, player.power + 1)
                elif enemy.etype == 'fast':
                    player.power = min(player.max_power, player.power + 2)
                elif enemy.etype == 'tank':
                    player.power = min(player.max_power, player.power + 4)

                exp = Explosion(enemy.rect.center, size=30 if enemy.etype != 'tank' else 45)
                effects.add(exp)
                all_sprites.add(exp)
                enemy.kill()

        # 敵弾 vs 自機
        if not player.invincible:
            hit_ebs = pygame.sprite.spritecollide(player, enemy_bullets, True)
            if hit_ebs:
                player.hit()
                exp = Explosion(player.rect.center, size=25)
                effects.add(exp); all_sprites.add(exp)

        # 敵本体 vs 自機
        if not player.invincible:
            hit_es = pygame.sprite.spritecollide(player, enemies, False,
                                                  pygame.sprite.collide_circle_ratio(0.7))
            if hit_es:
                player.hit()
                exp = Explosion(player.rect.center, size=25)
                effects.add(exp); all_sprites.add(exp)

        # ゲームオーバー判定
        if player.lives <= 0:
            game_over = True

        # ---------- 描画 ----------
        screen.fill(BLACK)
        if ser:
            try:
                ser.write(f"P:{player.power}\n".encode("utf-8"))
            except:
                pass

        for s in stars:
            s.draw(screen)

        for e in enemies:
            screen.blit(e.image, e.rect)
            e.draw_hp_bar(screen)

        for eb in enemy_bullets:
            screen.blit(eb.image, eb.rect)

        for b in bullets:
            screen.blit(b.image, b.rect)

        # 自機（Explosion effectより前）
        screen.blit(player.image, player.rect)

        for ef in effects:
            screen.blit(ef.image, ef.rect)

        draw_hud(screen, player, font, small_font, time_font, level, remaining_sec)

        pygame.display.flip()

    if ser:
        ser.close()
    pygame.quit()
    sys.exit()


def _do_bomb(player, enemies, effects, all_sprites):
    """ボム発動：全敵を破壊してスコア加算"""
    for e in list(enemies):
        player.score += e.score_val // 2  # ボムはスコア半分
        exp = Explosion(e.rect.center, size=25)
        effects.add(exp)
        all_sprites.add(exp)
        e.kill()
    flash = BombEffect()
    effects.add(flash)
    all_sprites.add(flash)

def _do_special_attack(player, bullets, all_sprites):
    speed = 12
    dirs = [
        (0, -speed),     # 上
        (0, speed),      # 下
        (-speed, 0),     # 左
        (speed, 0),      # 右
        (-8, -8),        # 左上
        (8, -8),         # 右上
        (-8, 8),         # 左下
        (8, 8),          # 右下
    ]

    for dx, dy in dirs:
        b = SpecialBullet(player.rect.centerx, player.rect.centery, dx, dy)
        bullets.add(b)
        all_sprites.add(b)


# ============================================================
if __name__ == '__main__':
    run_game()