import { test, expect } from '@playwright/test';
async function login(page:any,username:string){
 if(!process.env.PORTAL_DEMO_PASSWORD)throw new Error('Set PORTAL_DEMO_PASSWORD');
 await page.goto('/');await page.getByLabel('Username',{exact:true}).fill(username);
 await page.getByLabel('Password',{exact:true}).fill(process.env.PORTAL_DEMO_PASSWORD);
 await page.getByRole('button',{name:'Masuk ke workspace'}).click();await expect(page).toHaveURL(/\/portal$/);
}
test('student sees own outcomes and approved plans',async({page},info)=>{
 await login(page,'mahasiswa');
 await expect(page.getByRole('heading',{name:'Langkah belajar Anda berikutnya.'})).toBeVisible();
 await expect(page.getByText('STD-003',{exact:false}).first()).toBeVisible();
 await expect(page.getByText('STD-004',{exact:false})).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
 await page.screenshot({path:`/tmp/campus-student-${info.project.name}.png`,fullPage:true});
 await page.getByRole('button',{name:'Keluar',exact:true}).click();await expect(page.getByLabel('Password',{exact:true})).toBeVisible();
});
test('program portal shows only aggregated class outcomes',async({page},info)=>{
 await login(page,'prodi');
 await expect(page.getByRole('heading',{name:'Monitor capaian, arahkan perbaikan.'})).toBeVisible();
 await expect(page.getByText('CPL-01',{exact:true})).toBeVisible();
 await expect(page.getByText('STD-003',{exact:false})).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
 await page.screenshot({path:`/tmp/campus-prodi-${info.project.name}.png`,fullPage:true});
});
