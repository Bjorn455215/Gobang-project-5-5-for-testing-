#只能使用Python 3.10以下版本
import cv2 #4.13.0.92
import cvzone #1.6.1
from cvzone.HandTrackingModule import HandDetector
import numpy as np #2.0.2
import time

# 基礎設定
cap = cv2.VideoCapture(0)
cap.set(3, 1280)
cap.set(4, 720)

# 偵測手掌
detector = HandDetector(detectionCon=0.8, maxHands=1)

# 復古風格配色 (BGR)
color_board_bg = (160, 210, 240)  # 木質淺黃
color_grid = (40, 60, 80)        # 深褐色格線
color_ink = (25, 25, 25)         # 磨砂墨黑
color_ceramic = (240, 245, 250)  # 陶瓷白
color_stamp = (40, 40, 200)      # 硃砂紅 (用於勝負判定)
color_shadow = (100, 130, 150)   # 陰影色

# 遊戲變數
board_size = 5
grid_space = 100 # 格子間距
board_offset = (440, 160) # 棋盤線起點，畫面總寬是1280，這樣設可以讓棋盤(大小400)位在正中間
game_board = np.zeros((board_size, board_size))
current_turn = 1 # 1:黑, 2:白
game_over = False
win_text = ""
reset_timer = 0

class Piece():
    def __init__(self, pos, color_type):
        self.pos = pos
        self.color_type = color_type
        self.isDragging = False # 棋子初始狀態
        self.isPlaced = False # 棋盤位置初始狀態

    def update(self, cursor, is_pinched, already_grabbed):
        if self.isPlaced: return False
        cx, cy = self.pos #棋子的中心
        dist = np.sqrt((cursor[0]-cx)**2 + (cursor[1]-cy)**2) #計算手指和棋子的歐式距離

        # not already_grabbed: 防止一次抓起疊在一起的兩顆棋子
        # is_pinched: 大拇指和食指靠近才會觸發抓取動作
        if dist < 45 and not already_grabbed and is_pinched:
            self.pos = cursor # 棋子的座標 = 手指的座標
            self.isDragging = True # 棋子正在被拖曳
            return True # 回傳給主程式: 這隻手正在被使用
        self.isDragging = False # 否則回傳false
        return False

    def draw(self, imgUI):
        color = color_ink if self.color_type == 1 else color_ceramic
        # 繪製棋子陰影
        cv2.circle(imgUI, (self.pos[0]+3, self.pos[1]+3), 38, color_shadow, -1)
        # 繪製棋子本體
        cv2.circle(imgUI, self.pos, 38, color, -1)
        # 繪製細邊框增添質感
        border_c = (60, 60, 60) if self.color_type == 1 else (180, 180, 180)
        cv2.circle(imgUI, self.pos, 38, border_c, 2)

def check_win(board, p):
    for r in range(5): # row
        for c in range(5): # column
            if board[r][c] != p: continue # 只會判斷當前玩家下棋的顏色，其他玩家的棋子略過
            # 定義四個掃描方向：(Row偏移, Col偏移)
            # (0,1)  : 水平向右，列不變，行不斷 +1
            # (1,0)  : 垂直向下，行不變，列不斷 +1
            # (1,1)  : 右下斜對角，行列都+1
            # (1,-1) : 左下斜對角，列 +1，行 -1
            for dr, dc in [(0,1),(1,0),(1,1),(1,-1)]:
                count = 0
                for i in range(5): 
                    # 計算「目前起點」往「特定方向」走「i 步」後的位置，dr dc是方向向量
                    nr, nc = r + dr*i, c + dc*i

                    # 檢查一：這個位置有沒有超出棋盤 (0~4 之間)？
                    # 檢查二：這個位置的棋子是不是跟起點的人 (p) 一樣顏色？
                    if 0 <= nr < 5 and 0 <= nc < 5 and board[nr][nc] == p:
                        count += 1 # 條件符合就+1
                    else: break
                if count == 5: return True
    return False

# 自動計算文字標題座標: 置中用
left_center_x = 220   # 左圓中心
right_center_x = 1060  # 右圓中心

def draw_retro_text_centered(img, text, center_x, y, font_scale=1.5, thickness=3):
    (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_TRIPLEX, font_scale, thickness)
    start_x = center_x - w // 2
    
    cv2.putText(img, text, (start_x, y), cv2.FONT_HERSHEY_TRIPLEX, font_scale, color_board_bg, 8)
    
    # 硃砂紅文字(40 40 200)
    cv2.putText(img, text, (start_x, y), cv2.FONT_HERSHEY_TRIPLEX, font_scale, color_stamp, thickness)

# 計算勝場
def draw_scores(img, white_wins, black_wins, left_x, right_x):
    # 設定分數顯示的 Y 座標 (在圓圈下方)
    score_y = 560
    # 畫白棋勝場
    draw_retro_text_centered(img, f"WINS: {white_wins}", left_x, score_y, 1.0, 2)
    # 畫黑棋勝場
    draw_retro_text_centered(img, f"WINS: {black_wins}", right_x, score_y, 1.0, 2)

# 初始化分數變數
black_wins = 0
white_wins = 0
pieces_list = []
last_add_time = 0

while True:
    success, img = cap.read()
    if not success: break
    img = cv2.flip(img, 1) # 鏡像翻轉
    imgUI = np.zeros_like(img, np.uint8) #渲染新畫布用
    hands, img = detector.findHands(img, flipType=False, draw=True) #前面手動翻轉過了不再重翻一次

    turn_label = "TURN: BLACK" if current_turn == 1 else "TURN: WHITE" #回合交換
    
    # 1. 繪製復古棋盤底座: cv2.rectangle(影像, 左上角座標, 右下角座標, 顏色, 線條粗細)
    cv2.rectangle(imgUI, (board_offset[0]-30, board_offset[1]-30), 
                 (board_offset[0]+430, board_offset[1]+430), color_board_bg, -1) # 填滿顏色
    cv2.rectangle(imgUI, (board_offset[0]-30, board_offset[1]-30), 
                 (board_offset[0]+430, board_offset[1]+430), color_grid, 4) # 畫邊框

    # 2. 畫生成區 (改為圓形棋罐感)，棋子半徑100
    '''# 左白區，左側(150 360)
    cv2.circle(imgUI, (150, 360), 150, color_board_bg, -1) # -1 填滿顏色
    cv2.circle(imgUI, (150, 360), 150, color_grid, 3) # 3 線條粗細
    #cv2.putText(影像, 文字內容, 座標, 字體, 大小, 顏色, 粗細)
    cv2.putText(imgUI, "WHITE SITE", (40, 190), cv2.FONT_HERSHEY_TRIPLEX, 1.5 , color_grid, 3)'''
    # 自動計算左側白棋區文字及圓圈置中
    cv2.circle(imgUI, (left_center_x, 360), 150, color_board_bg, -1)
    cv2.circle(imgUI, (left_center_x, 360), 150, color_grid, 3)
    draw_retro_text_centered(imgUI, "WHITE SITE", left_center_x, 190)

    '''# 右黑區，右側(1130 360)
    cv2.circle(imgUI, (1130, 360), 150, color_board_bg, -1)
    cv2.circle(imgUI, (1130, 360), 150, color_grid, 3)
    cv2.putText(imgUI, "BLACK SITE", (960, 190), cv2.FONT_HERSHEY_TRIPLEX, 1.5, color_grid, 3)'''
    # 自動計算右側黑棋區文字及圓圈置中
    cv2.circle(imgUI, (right_center_x, 360), 150, color_board_bg, -1)
    cv2.circle(imgUI, (right_center_x, 360), 150, color_grid, 3)
    draw_retro_text_centered(imgUI, "BLACK SITE", right_center_x, 190)

    # 回合提示置中(螢幕中心: 1280/2 = 640)
    draw_retro_text_centered(imgUI, turn_label, 640, 80)
    
    # 勝場標示
    draw_scores(imgUI, white_wins, black_wins, left_center_x, right_center_x)

    # 3. 畫棋盤格線
    # i*grid_space: 計算等距離偏移量，「第幾格 * 每格寬度」，讓電腦畫出整齊網格的基礎公式
    for i in range(board_size):
        cv2.line(imgUI, (board_offset[0], board_offset[1] + i*grid_space), 
                 (board_offset[0] + 400, board_offset[1] + i*grid_space), color_grid, 2) #橫線起點和終點
        cv2.line(imgUI, (board_offset[0] + i*grid_space, board_offset[1]), 
                 (board_offset[0] + i*grid_space, board_offset[1] + 400), color_grid, 2) #直線起點和終點

    if hands and not game_over: # 偵測到手，還未遊戲結束
        lmList = hands[0]['lmList'] #取畫面中一隻手，並包含該手 21 個點的二維列表
        p4, p8 = lmList[4][:2], lmList[8][:2] # 取大拇指和食指的二維數據
        grasp_point = [(p4[0] + p8[0]) // 2, (p4[1] + p8[1]) // 2]
        
        # 只取大拇指和和食指的距離資料，不取資訊、繪圖後影像，因用 _ 略過
        dist1, _, _ = detector.findDistance(p4, p8) 
        is_pinched = dist1 < 50
        
        # 生成邏輯 (張開手)
        if dist1 > 160 and (time.time() - last_add_time > 1.2):
            # 只有當場上「所有棋子都已就位」時，才准許生成新棋子。
            if not any(not p.isPlaced for p in pieces_list):
                if grasp_point[0] > 910 and current_turn == 1: # 在右側時，生成一個黑子
                    pieces_list.append(Piece(grasp_point, 1))
                    last_add_time = time.time()
                elif grasp_point[0] < 370 and current_turn == 2: # 在左側時，生成一個白子
                    pieces_list.append(Piece(grasp_point, 2))
                    last_add_time = time.time()

        # 拖拽與落子
        already_grabbed = False
        for p in reversed(pieces_list):
            was_dragging = p.isDragging # 上一幀狀態改成正在拖曳
            if p.update(grasp_point, is_pinched, already_grabbed):
                already_grabbed = True # 告訴系統已經有手在抓取了，不能再抓第二顆
            
            if was_dragging and not is_pinched:
                # 如果上一幀還在拖拽（was_dragging），但這一幀放開了（not is_pinched），觸發落子。
                # 計算棋子大概放置的位置
                gx = round((p.pos[0] - board_offset[0]) / grid_space)
                gy = round((p.pos[1] - board_offset[1]) / grid_space)
                
                # 如果下在棋盤範圍內，而且該格子上沒有棋子，才能觸發落子
                if 0 <= gx < board_size and 0 <= gy < board_size and game_board[gy][gx] == 0:
                    # 將棋子座標強制對齊到格點中心
                    p.pos = (board_offset[0] + gx * grid_space, board_offset[1] + gy * grid_space)
                    p.isPlaced = True #棋子鎖定
                    game_board[gy][gx] = p.color_type # 存進矩陣，讓系統知道這個位置有棋子
                    if check_win(game_board, p.color_type):
                        if not game_over: # 確保只加一次分
                            if p.color_type == 1:
                                black_wins += 1
                            else:
                                white_wins += 1
                            game_over = True # 鎖定狀態，防止重覆加分
                        win_text = "BLACK WINS" if p.color_type == 1 else "WHITE WINS"
                        reset_timer = time.time()

                    current_turn = 3 - current_turn # 不管有沒有人贏都要切換回合，1: 白變黑、2: 黑變白
                else:
                    if not p.isPlaced: pieces_list.remove(p) # 落子失敗

    for p in pieces_list:
        p.draw(imgUI) # 把棋子畫上畫布

    # 勝利提示 (使用朱紅印章色)，狀態重置
    if game_over:
        cv2.putText(imgUI, win_text, (420, 380), cv2.FONT_HERSHEY_TRIPLEX, 2.5, color_stamp, 3)
        if time.time() - reset_timer > 5: # 遊戲結束後5秒重置棋盤
            game_board.fill(0)
            pieces_list = []
            game_over = False
            current_turn = 1

    # 回合顯示置中
    draw_retro_text_centered(imgUI, turn_label, 640, 80, font_scale=1.5, thickness=3)

    # 最終疊加 (調高背景權重使木質感更實)
    alpha = 0.8 
    out = cv2.addWeighted(img, 1 - alpha, imgUI, alpha, 0)
    cv2.imshow("Retro Gobang 5x5", out)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
