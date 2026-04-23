import pygame
import sys
 
pygame.init()
screen = pygame.display.set_mode((640, 480))
clock = pygame.time.Clock()
 
running = True
while running:
    # 入力処理
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
 
    # 更新処理（ゲームロジックなど）
 
    # 描画処理
    screen.fill((0, 0, 0))  # 黒で画面クリア
    # ここに描画コードを追加
    pygame.display.flip()   # 表示を更新
 
    # フレームレート制御（例：60FPS）
    clock.tick(60)
 
pygame.quit()
sys.exit()
