export default function Login() {
  return (
    <main className="min-h-screen grid place-items-center p-8">
      <div className="max-w-sm w-full bg-white rounded-2xl shadow p-8 text-center space-y-6">
        <h1 className="text-2xl font-semibold">transcribe-cloud</h1>
        <p className="text-slate-600">Sign in with your Pocket ID account to continue.</p>
        <a
          href="/api/auth/login"
          className="block w-full rounded-xl bg-slate-900 text-white font-medium py-3 hover:bg-slate-800 transition"
        >
          Sign in with Pocket ID
        </a>
      </div>
    </main>
  );
}
