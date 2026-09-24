import logging

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    import customtkinter as ctk

    from src.modules.main.main_window import SavTool

    root = ctk.CTk()
    app = SavTool(root)
    root.mainloop()
