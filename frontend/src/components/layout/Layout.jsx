import { Outlet } from "react-router-dom";
import Header from "./Header";
import Footer from "./Footer";

export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col bg-paper">
      <Header />
      <main className="flex-1 w-full max-w-[1040px] mx-auto px-5 sm:px-7 py-10">
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
