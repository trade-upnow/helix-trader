import { LoginForm } from "@/components/login-form";
import { SiteHeader } from "@/components/site-header";

export default function LoginPage() {
  return (
    <main className="min-h-screen pb-16">
      <SiteHeader />
      <div className="mx-auto flex w-full max-w-7xl px-6 py-10 lg:px-10">
        <LoginForm />
      </div>
    </main>
  );
}
