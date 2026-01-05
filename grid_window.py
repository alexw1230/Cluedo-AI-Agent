import tkinter as tk
from tkinter import font

class GridWindow:
    def __init__(self, n, row_labels, col_labels):
        #Assertions
        assert len(row_labels) == 21, "row labels must be len 21"
        assert len(col_labels) == n - 1, "col labels must be len n-1"
        
        #Grid dimensions
        self.n = n
        self.rows = n
        self.cols = 22

        #Labels
        self.row_labels = row_labels
        self.col_labels = col_labels

        #Colors
        self.neutral_color = "#EDE8D0"  
        self.green_color = "#1db43e"    
        self.red_color = "#ab1717"
        self.label_color = "#A9A9A9"

        #Basic window init
        self.root = tk.Tk()
        self.root.title("Clue AI Agent")

        #Font & Cell size
        self.font = font.Font(family="Arial", size=11)
        self.cell_size = self._compute_cell_size()

        #Main canvas dimensions
        width = self.cols * self.cell_size
        height = self.rows * self.cell_size + 30
        self.canvas = tk.Canvas(self.root, width=width, height=height)
        self.canvas.pack()

        self.rects = [[None for _ in range(self.cols)] for _ in range(self.rows)]

        self._create_grid()

        #Rescale
        self.rescale_btn = tk.Button(self.root, text="Rescale Grid", command=self._rescale_cells)
        self.rescale_btn.pack(side=tk.BOTTOM, pady=5)

    #Cell size to fit larget label neatly
    def _compute_cell_size(self):
        max_dim = 0
        for label in self.row_labels + self.col_labels:
            w = self.font.measure(str(label))
            h = self.font.metrics("linespace")
            max_dim = max(max_dim, w, h)
        return max_dim + 4

    #Draws grid
    def _create_grid(self):
        #Draw cells
        for r in range(self.rows):
            for c in range(self.cols):
                x1 = c * self.cell_size
                y1 = r * self.cell_size
                x2 = x1 + self.cell_size
                y2 = y1 + self.cell_size

                if r == 0 and c == 0:
                    fill_color = "black"
                else:
                    fill_color = self.neutral_color

                self.rects[r][c] = self.canvas.create_rectangle(
                    x1, y1, x2, y2,
                    fill=fill_color,
                    width=2,
                    outline="gray"
                )
        #Row labels
        for c in range(1, self.cols):
            x = c * self.cell_size
            y = 0
            self.canvas.create_rectangle(
                x, y, x+self.cell_size, y+self.cell_size,
                fill=self.label_color, outline="gray", width=2
            )
            self.canvas.create_text(
                x + self.cell_size / 2,
                y + self.cell_size / 2,
                text=str(self.row_labels[c-1]),
                font=self.font,
                fill="black"
            )
        #Col labels
        for r in range(1, self.rows):
            x = 0
            y = r * self.cell_size
            self.canvas.create_rectangle(
                x, y, x+self.cell_size, y+self.cell_size,
                fill=self.label_color, outline="gray", width=2
            )
            self.canvas.create_text(
                x + self.cell_size / 2,
                y + self.cell_size / 2,
                text=str(self.col_labels[r-1]),
                font=self.font,
                fill="black"
            )
    #Rescale
    def _rescale_cells(self):
        current_width = self.root.winfo_width()
        new_cell_size = current_width // self.cols
        self.cell_size = new_cell_size
        self.canvas.delete("all")
        self._create_grid()
    #Update with data
    def update(self, matrix):
        for r in range(21):
            for c in range(self.n - 1):
                val = matrix[r][c]
                grid_r = c + 1
                grid_c = r + 1

                if val == 1:
                    color = self.green_color
                elif val == -1:
                    color = self.red_color
                else:
                    color = self.neutral_color

                self.canvas.itemconfig(self.rects[grid_r][grid_c], fill=color)

        self.root.update_idletasks()
        
    #Standard
    def run(self):
        self.root.mainloop()
